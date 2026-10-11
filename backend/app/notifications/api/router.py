"""REST API endpoints for the notification module."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.auth.authorization import (
    authenticated,
    require_ack,
    require_admin,
    require_notification_write,
)
from app.auth.dependencies import AuthenticatedUser
from app.database.infrastructure.models import AlertORM
from app.database.infrastructure.repositories import (
    AlertRepository,
    NotificationRepository,
)
from app.database.infrastructure.session import get_db
from app.events.domain import Alert
from app.notifications.application import (
    AlertAcknowledgementService,
    NotificationService,
)
from app.notifications.domain import (
    Notification,
    NotificationChannel,
    NotificationStatus,
)

logger = logging.getLogger(__name__)
_audit = AuditService()
_alert_repo = AlertRepository()
_notif_repo = NotificationRepository()

# Persistent-history defaults: bounded reads; the runtime (in-memory)
# /history endpoint stays uncapped as the volatile prototype.
PERSISTENT_HISTORY_DEFAULT_LIMIT = 50
PERSISTENT_HISTORY_MAX_LIMIT = 200
REDISPATCHABLE_STATUSES = frozenset({"pending", "failed", "disabled"})

router = APIRouter(prefix="/notifications", tags=["notifications"])

__all__ = ["router"]


# ---------------------------------------------------------------------------
# Pydantic Request / Response Schemas
# ---------------------------------------------------------------------------

class AlertSummary(BaseModel):
    id: str
    device_id: str
    user_id: str
    type: str
    message: str
    criticality: float
    acknowledged: bool
    created_at: str


class NotificationResponse(BaseModel):
    id: str
    alert_id: str
    channel: str
    status: str
    notification_date: str
    alert: Optional[AlertSummary] = None


class NotificationHistoryResponse(BaseModel):
    count: int
    notifications: list[NotificationResponse]


class AcknowledgeAlertRequest(BaseModel):
    # Accepted for backward compatibility but IGNORED: the acting
    # user always comes from the validated token (TSK-055).
    user_id: Optional[str] = None
    acknowledged: Optional[bool] = True


class UpdateNotificationStatusRequest(BaseModel):
    status: str


class NotificationProcessRequest(BaseModel):
    alert_id: Optional[str] = None
    recipient: Optional[str] = None
    message: Optional[str] = None
    device_id: Optional[str] = None
    # Accepted for backward compatibility but IGNORED: the alert
    # owner is always the authenticated user (TSK-055).
    user_id: Optional[str] = None
    type: Optional[str] = None
    criticality: Optional[float] = None
    # Manual redispatch of a failed/disabled/pending delivery (Fase C).
    # Without force, reprocessing an already-recorded (alert, channel,
    # recipient) returns the existing row without re-sending. With
    # force=True and an existing failed/disabled/pending row, the delivery
    # is attempted again and the SAME row is updated (no duplicate rows,
    # no retry daemon). Already sent/simulated rows are never re-sent.
    force: bool = False


class PersistentNotificationResponse(BaseModel):
    id: str
    alert_id: str
    channel: str
    status: str
    notification_date: str
    is_read: bool
    read_at: Optional[str] = None
    alert: Optional[AlertSummary] = None


class PersistentHistoryResponse(BaseModel):
    count: int
    notifications: list[PersistentNotificationResponse]


class UnreadCountResponse(BaseModel):
    unread: int


# ---------------------------------------------------------------------------
# Helpers & Serializers
# ---------------------------------------------------------------------------

def _validated_limit(limit: Optional[int]) -> Optional[int]:
    """Validate a query limit and return a normalized positive integer."""
    if limit is None:
        return None
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'limit' must be a positive integer.",
        )
    if limit <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'limit' must be greater than zero.",
        )
    return limit


def _validate_uuid(val: str, field_name: str = "id") -> UUID:
    try:
        return UUID(val)
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{field_name}' must be a valid UUID.",
        ) from exc


def _serialize_alert(alert: Alert) -> dict[str, Any]:
    return {
        "id": str(alert.id),
        "device_id": str(alert.device_id),
        "user_id": str(alert.user_id),
        "type": alert.type,
        "message": alert.message,
        "criticality": float(alert.criticality),
        "acknowledged": bool(alert.acknowledged),
        "created_at": alert.created_at.isoformat(timespec="seconds")
        if hasattr(alert.created_at, "isoformat")
        else str(alert.created_at),
    }


def _serialize_notification(
    notification: Notification, alerts_list: list[Alert] | None = None
) -> dict[str, Any]:
    channel_val = (
        notification.channel.value
        if hasattr(notification.channel, "value")
        else str(notification.channel)
    )
    status_val = (
        notification.status.value
        if hasattr(notification.status, "value")
        else str(notification.status)
    )
    date_val = (
        notification.notification_date.isoformat(timespec="seconds")
        if hasattr(notification.notification_date, "isoformat")
        else str(notification.notification_date)
    )

    alert_data = None
    if notification.alert is not None:
        alert_data = _serialize_alert(notification.alert)
    elif alerts_list:
        for alert in alerts_list:
            if alert.id == notification.alert_id:
                alert_data = _serialize_alert(alert)
                break

    result: dict[str, Any] = {
        "id": str(notification.id),
        "alert_id": str(notification.alert_id),
        "channel": channel_val,
        "status": status_val,
        "notification_date": date_val,
    }
    if alert_data is not None:
        result["alert"] = alert_data

    return result


def _serialize_alert_row(row: AlertORM) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "device_id": str(row.device_id),
        "user_id": str(row.user_id),
        "type": row.type,
        "message": row.message,
        "criticality": float(row.criticality),
        "acknowledged": bool(row.acknowledged),
        "created_at": row.created_at.isoformat(timespec="seconds")
        if hasattr(row.created_at, "isoformat")
        else str(row.created_at),
    }


def _serialize_persistent(row, alert_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Serialize a NotificationORM row. Shape mirrors the runtime
    serializer plus owner read state (is_read/read_at)."""
    date_val = (
        row.notification_date.isoformat(timespec="seconds")
        if hasattr(row.notification_date, "isoformat")
        else str(row.notification_date)
    )
    result: dict[str, Any] = {
        "id": str(row.id),
        "alert_id": str(row.alert_id),
        "channel": str(row.channel),
        "status": str(row.status),
        "notification_date": date_val,
        "is_read": bool(row.is_read),
        "read_at": (
            row.read_at.isoformat(timespec="seconds")
            if row.read_at is not None and hasattr(row.read_at, "isoformat")
            else (str(row.read_at) if row.read_at is not None else None)
        ),
    }
    if alert_data is not None:
        result["alert"] = alert_data
    return result


def _parse_is_read(raw: Optional[str]) -> Optional[bool]:
    if raw is None:
        return None
    normalized = raw.strip().lower()
    if normalized in ("true", "1", "yes"):
        return True
    if normalized in ("false", "0", "no"):
        return False
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Invalid is_read '{raw}'. Must be true or false.",
    )


def _alert_summaries(db: Session, alert_ids: set[UUID]) -> dict[UUID, dict[str, Any]]:
    if not alert_ids:
        return {}
    rows = db.query(AlertORM).filter(AlertORM.id.in_(list(alert_ids))).all()
    return {row.id: _serialize_alert_row(row) for row in rows}


def _get_notifications_list(request: Request) -> list[Notification]:
    notifications = getattr(request.app.state, "notifications", None)
    if notifications is None:
        notifications = []
        request.app.state.notifications = notifications
    return notifications


def _get_alerts_list(request: Request) -> list[Alert]:
    alerts = getattr(request.app.state, "alerts", None)
    if alerts is None:
        alerts = []
        request.app.state.alerts = alerts
    return alerts


def _find_alert_by_id(request: Request, alert_uuid: UUID) -> Optional[Alert]:
    # 1. Search in app.state.alerts
    alerts_list = _get_alerts_list(request)
    for alert in alerts_list:
        if alert.id == alert_uuid:
            return alert

    # 2. Search in app.state.notifications' attached alert
    notifications_list = _get_notifications_list(request)
    for notif in notifications_list:
        if notif.alert is not None and notif.alert.id == alert_uuid:
            return notif.alert
        if notif.alert_id == alert_uuid and notif.alert is not None:
            return notif.alert

    return None


def _get_notification_service(request: Request) -> NotificationService:
    service = getattr(request.app.state, "notification_service", None)
    if service is None:
        service = NotificationService()
        request.app.state.notification_service = service
    return service


def _get_ack_service(request: Request) -> AlertAcknowledgementService:
    ack_service = getattr(request.app.state, "alert_acknowledgement_service", None)
    if ack_service is None:
        ack_service = AlertAcknowledgementService()
        request.app.state.alert_acknowledgement_service = ack_service
    return ack_service


# ---------------------------------------------------------------------------
# Endpoints: History & Listing
# ---------------------------------------------------------------------------

@router.get("", response_model=NotificationHistoryResponse)
@router.get("/", response_model=NotificationHistoryResponse)
@router.get("/history", response_model=NotificationHistoryResponse)
def get_notifications_history(
    request: Request,
    limit: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    channel: Optional[str] = Query(None),
    alert_id: Optional[str] = Query(None),
    _current: AuthenticatedUser = Depends(authenticated),
):
    """Retrieve notification history with optional filtering and pagination."""
    normalized_limit = _validated_limit(limit)

    norm_status: Optional[str] = None
    if status_filter is not None:
        s = status_filter.strip().lower()
        valid_statuses = {st.value for st in NotificationStatus}
        if s not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status '{status_filter}'. Must be one of {sorted(valid_statuses)}.",
            )
        norm_status = s

    norm_channel: Optional[str] = None
    if channel is not None:
        c = channel.strip().lower()
        valid_channels = {ch.value for ch in NotificationChannel}
        if c not in valid_channels:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid channel '{channel}'. Must be one of {sorted(valid_channels)}.",
            )
        norm_channel = c

    filter_alert_uuid: Optional[UUID] = None
    if alert_id is not None:
        filter_alert_uuid = _validate_uuid(alert_id, "alert_id")

    notifications_list = _get_notifications_list(request)
    alerts_list = _get_alerts_list(request)

    filtered = []
    for notif in notifications_list:
        notif_status = (
            notif.status.value if hasattr(notif.status, "value") else str(notif.status)
        )
        notif_channel = (
            notif.channel.value if hasattr(notif.channel, "value") else str(notif.channel)
        )

        if norm_status is not None and notif_status != norm_status:
            continue
        if norm_channel is not None and notif_channel != norm_channel:
            continue
        if filter_alert_uuid is not None and notif.alert_id != filter_alert_uuid:
            continue

        filtered.append(notif)

    if normalized_limit is not None:
        filtered = filtered[-normalized_limit:]

    serialized_items = [
        _serialize_notification(notif, alerts_list) for notif in filtered
    ]
    return {"count": len(serialized_items), "notifications": serialized_items}


# ---------------------------------------------------------------------------
# Endpoints: Persistent history & read state (Fase C)
#
# Durable, owner-scoped views over the notifications table. Every endpoint
# filters by the authenticated user's id: a user only ever sees or mutates
# their own rows (unknown/foreign ids answer 404, never 403, to avoid
# existence oracles). Read state (is_read/read_at) is fully independent
# from Alert.acknowledged in both directions.
# NOTE: single-segment GETs must stay registered BEFORE /{notification_id}
# below, otherwise Starlette would route them as a notification id.
# ---------------------------------------------------------------------------

@router.get("/persistent", response_model=PersistentHistoryResponse)
def get_persistent_history(
    limit: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    channel: Optional[str] = Query(None),
    alert_id: Optional[str] = Query(None),
    is_read: Optional[str] = Query(None),
    current: AuthenticatedUser = Depends(authenticated),
    db: Session = Depends(get_db),
):
    """Owner-scoped persistent notification history, newest first."""
    normalized_limit = _validated_limit(limit)
    if normalized_limit is None:
        normalized_limit = PERSISTENT_HISTORY_DEFAULT_LIMIT
    if normalized_limit > PERSISTENT_HISTORY_MAX_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'limit' must be <= {PERSISTENT_HISTORY_MAX_LIMIT}.",
        )

    norm_status: Optional[str] = None
    if status_filter is not None:
        s = status_filter.strip().lower()
        valid_statuses = {st.value for st in NotificationStatus}
        if s not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status '{status_filter}'. Must be one of {sorted(valid_statuses)}.",
            )
        norm_status = s

    norm_channel: Optional[str] = None
    if channel is not None:
        c = channel.strip().lower()
        valid_channels = {ch.value for ch in NotificationChannel}
        if c not in valid_channels:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid channel '{channel}'. Must be one of {sorted(valid_channels)}.",
            )
        norm_channel = c

    filter_alert_uuid: Optional[UUID] = None
    if alert_id is not None:
        filter_alert_uuid = _validate_uuid(alert_id, "alert_id")
    read_flag = _parse_is_read(is_read)

    rows = _notif_repo.list_by_owner(
        db,
        current.id,
        status=norm_status,
        channel=norm_channel,
        alert_id=filter_alert_uuid,
        is_read=read_flag,
        limit=normalized_limit,
    )
    summaries = _alert_summaries(db, {row.alert_id for row in rows})
    return {
        "count": len(rows),
        "notifications": [
            _serialize_persistent(row, summaries.get(row.alert_id)) for row in rows
        ],
    }


@router.get("/unread-count", response_model=UnreadCountResponse)
def get_unread_count(
    current: AuthenticatedUser = Depends(authenticated),
    db: Session = Depends(get_db),
):
    """Number of owned notifications not yet read (bell badge source)."""
    return {"unread": _notif_repo.count_unread(db, current.id)}


@router.patch("/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    current: AuthenticatedUser = Depends(authenticated),
    db: Session = Depends(get_db),
):
    """Mark one owned notification as read. Idempotent; never touches
    the linked alert's acknowledgement."""
    notif_uuid = _validate_uuid(notification_id, "notification_id")
    try:
        row = _notif_repo.mark_read(db, notif_uuid, current.id)
    except Exception:
        logger.warning("notification.read skipped (no reachable DB)")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notification store is not reachable.",
        )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )
    # The read commits FIRST so it is never lost when auditing is
    # unavailable; the audit trail itself stays best-effort.
    try:
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notification store is not reachable.",
        )
    summaries = _alert_summaries(db, {row.alert_id})
    _audit_best_effort(
        db,
        actor_id=current.id,
        action="notification.read",
        resource=f"notifications/{row.id}",
        old_value={"is_read": False},
        new_value={"is_read": True},
    )
    return {
        "message": "Notification marked as read",
        "notification": _serialize_persistent(row, summaries.get(row.alert_id)),
    }


@router.post("/read-all")
def mark_all_notifications_read(
    current: AuthenticatedUser = Depends(authenticated),
    db: Session = Depends(get_db),
):
    """Mark all owned unread notifications as read. Returns rows updated."""
    try:
        updated = _notif_repo.mark_all_read(db, current.id)
        db.commit()
    except Exception:
        logger.warning("notification.read_all skipped (no reachable DB)")
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notification store is not reachable.",
        )
    _audit_best_effort(
        db,
        actor_id=current.id,
        action="notification.read_all",
        resource="notifications",
        new_value={"updated": updated},
    )
    return {"updated": updated}


# ---------------------------------------------------------------------------
# Endpoints: Single Notification
# ---------------------------------------------------------------------------

@router.get("/{notification_id}")
def get_notification_by_id(
    request: Request,
    notification_id: str,
    _current: AuthenticatedUser = Depends(authenticated),
):
    """Retrieve a single notification record by its identifier."""
    notif_uuid = _validate_uuid(notification_id, "notification_id")
    notifications_list = _get_notifications_list(request)
    alerts_list = _get_alerts_list(request)

    for notif in notifications_list:
        if notif.id == notif_uuid:
            serialized = _serialize_notification(notif, alerts_list)
            return {"notification": serialized, **serialized}

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Notification not found.",
    )


@router.get("/{notification_id}/status")
def get_notification_status(
    request: Request,
    notification_id: str,
    _current: AuthenticatedUser = Depends(authenticated),
):
    """Consult the current status of a notification."""
    notif_uuid = _validate_uuid(notification_id, "notification_id")
    notifications_list = _get_notifications_list(request)
    alerts_list = _get_alerts_list(request)

    for notif in notifications_list:
        if notif.id == notif_uuid:
            serialized = _serialize_notification(notif, alerts_list)
            status_val = (
                notif.status.value
                if hasattr(notif.status, "value")
                else str(notif.status)
            )
            return {
                "id": str(notif.id),
                "status": status_val,
                "notification": serialized,
                **serialized,
            }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Notification not found.",
    )


@router.patch("/{notification_id}/status")
@router.put("/{notification_id}/status")
@router.patch("/{notification_id}")
def update_notification_status(
    request: Request,
    notification_id: str,
    body: UpdateNotificationStatusRequest,
    _current: AuthenticatedUser = Depends(require_notification_write),
    db: Session = Depends(get_db),
):
    """Update delivery status of a notification."""
    notif_uuid = _validate_uuid(notification_id, "notification_id")
    raw_status = body.status.strip().lower()
    valid_statuses = {st.value for st in NotificationStatus}
    if raw_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{body.status}'. Must be one of {sorted(valid_statuses)}.",
        )

    notifications_list = _get_notifications_list(request)
    alerts_list = _get_alerts_list(request)

    for notif in notifications_list:
        if notif.id == notif_uuid:
            old_status = (
                notif.status.value
                if hasattr(notif.status, "value")
                else str(notif.status)
            )
            notif.status = NotificationStatus(raw_status)
            # TSK-059.5 — audit validated transition with old/new values.
            _audit_best_effort(
                db,
                actor_id=_current.id,
                action="notification.status",
                resource=f"notifications/{notif.id}",
                old_value={"status": old_status},
                new_value={"status": raw_status},
            )
            serialized = _serialize_notification(notif, alerts_list)
            return {
                "message": "Notification status updated successfully",
                "notification": serialized,
                **serialized,
            }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Notification not found.",
    )


# ---------------------------------------------------------------------------
# Endpoints: Alert Acknowledgement & Alert Status
# ---------------------------------------------------------------------------

def _audit_best_effort(
    db: Session | None,
    *,
    actor_id: UUID,
    action: str,
    resource: str,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    """Record audit in the caller's session when a DB is reachable.

    TSK-059.5 — notifications/alerts live primarily in app.state (runtime).
    When no database is reachable (isolated test apps), audit is skipped so
    runtime behavior is preserved; in production the DB is always present.
    """
    if db is None:
        return
    try:
        _audit.record(
            db,
            actor_user_id=actor_id,
            action=action,
            resource=resource,
            old_value=old_value,
            new_value=new_value,
        )
        db.commit()
    except Exception:
        logger.warning("audit record for %s skipped (no reachable DB)", action)
        try:
            db.rollback()
        except Exception:
            pass


def _persist_acknowledgement(db: Session | None, alert_uuid: UUID) -> bool | None:
    """Persist acknowledged=True for a stored alert row.

    Returns previous acknowledged flag, or None when no DB row exists or no
    DB is reachable. TSK-059.5 — AlertORM is the persistent source; app.state
    stays the runtime/cache source and is synced by the caller.
    """
    if db is None:
        return None
    try:
        row = _alert_repo.get_by_id(db, alert_uuid)
        if row is None:
            return None
        was_acknowledged = bool(row.acknowledged)
        row.acknowledged = True
        db.flush()
        return was_acknowledged
    except Exception:
        logger.warning("alert ack persistence skipped (no reachable DB)")
        try:
            db.rollback()
        except Exception:
            pass
        return None


def _perform_acknowledgement(
    request: Request,
    alert_uuid: UUID,
    actor: AuthenticatedUser,
    db: Session | None = None,
) -> dict[str, Any]:
    alert = _find_alert_by_id(request, alert_uuid)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found.",
        )

    # TSK-055: the acting user comes from the validated token.
    # Any client-provided user_id is ignored by the callers.
    ack_service = _get_ack_service(request)
    updated_alert = ack_service.acknowledge(alert, user_id=actor.id)

    # Ensure any notifications linking to this alert are in sync
    notifications_list = _get_notifications_list(request)
    for notif in notifications_list:
        if notif.alert_id == alert_uuid and notif.alert is not None:
            notif.alert.acknowledged = True

    # TSK-059.5 — persist when the alert row exists; audit in the same session.
    # First execution: old=false/new=true; idempotent repeat: NULLs.
    if db is not None:
        try:
            was_acknowledged = _persist_acknowledgement(db, alert_uuid)
            if was_acknowledged is not None:
                old_new = (
                    (None, None)
                    if was_acknowledged
                    else ({"acknowledged": False}, {"acknowledged": True})
                )
                _audit.record(
                    db,
                    actor_user_id=actor.id,
                    action="alert.acknowledge",
                    resource=f"alerts/{alert_uuid}",
                    old_value=old_new[0],
                    new_value=old_new[1],
                )
            db.commit()
        except Exception:
            logger.warning("alert ack persistence/audit skipped (no reachable DB)")
            try:
                db.rollback()
            except Exception:
                pass

    serialized_alert = _serialize_alert(updated_alert)
    return {
        "message": "Alert acknowledged successfully",
        "alert_id": str(updated_alert.id),
        "acknowledged": updated_alert.acknowledged,
        "alert": serialized_alert,
        **serialized_alert,
    }


@router.post("/alerts/{alert_id}/acknowledge")
@router.post("/alerts/{alert_id}/ack")
@router.post("/acknowledge/{alert_id}")
def acknowledge_alert(
    request: Request,
    alert_id: str,
    body: Optional[AcknowledgeAlertRequest] = None,
    current: AuthenticatedUser = Depends(require_ack),
    db: Session = Depends(get_db),
):
    """Register acknowledgement of an Alert by the authenticated user."""
    alert_uuid = _validate_uuid(alert_id, "alert_id")
    return _perform_acknowledgement(request, alert_uuid, current, db)


@router.post("/acknowledge")
def acknowledge_alert_body(
    request: Request,
    body: dict[str, Any],
    current: AuthenticatedUser = Depends(require_ack),
    db: Session = Depends(get_db),
):
    """Register acknowledgement where alert_id is provided in request body."""
    raw_alert_id = body.get("alert_id")
    if not raw_alert_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'alert_id' must be provided in request body.",
        )
    alert_uuid = _validate_uuid(str(raw_alert_id), "alert_id")
    return _perform_acknowledgement(request, alert_uuid, current, db)


@router.post("/{notification_id}/acknowledge")
def acknowledge_via_notification(
    request: Request,
    notification_id: str,
    body: Optional[AcknowledgeAlertRequest] = None,
    current: AuthenticatedUser = Depends(require_ack),
    db: Session = Depends(get_db),
):
    """Acknowledge the alert associated with a specific notification."""
    notif_uuid = _validate_uuid(notification_id, "notification_id")
    notifications_list = _get_notifications_list(request)

    target_notif = None
    for notif in notifications_list:
        if notif.id == notif_uuid:
            target_notif = notif
            break

    if target_notif is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )

    user_id = body.user_id if body else None
    _ = user_id  # ignored: actor comes from the token (TSK-055)
    ack_result = _perform_acknowledgement(request, target_notif.alert_id, current, db)
    if target_notif.alert is not None:
        target_notif.alert.acknowledged = True

    serialized_notif = _serialize_notification(target_notif, _get_alerts_list(request))
    return {
        **ack_result,
        "notification": serialized_notif,
    }


@router.get("/alerts/{alert_id}")
@router.get("/alerts/{alert_id}/status")
def get_alert_status(
    request: Request,
    alert_id: str,
    _current: AuthenticatedUser = Depends(authenticated),
):
    """Consult the status of an alert and associated notifications."""
    alert_uuid = _validate_uuid(alert_id, "alert_id")
    alert = _find_alert_by_id(request, alert_uuid)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found.",
        )

    notifications_list = _get_notifications_list(request)
    matching_notifications = [
        _serialize_notification(notif, _get_alerts_list(request))
        for notif in notifications_list
        if notif.alert_id == alert_uuid
    ]

    serialized_alert = _serialize_alert(alert)
    return {
        "alert_id": str(alert.id),
        "acknowledged": alert.acknowledged,
        "alert": serialized_alert,
        "notifications": matching_notifications,
        **serialized_alert,
    }


# ---------------------------------------------------------------------------
# Endpoints: Processing / Dispatching Notifications
# ---------------------------------------------------------------------------

@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
@router.post("/process", status_code=status.HTTP_201_CREATED)
def process_notification(
    request: Request,
    body: NotificationProcessRequest,
    current: AuthenticatedUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Process an alert through NotificationService to generate and send a notification.

    Admin-only manual alert creation (TSK-055). The alert owner is
    always the authenticated user; any client-provided user_id is
    ignored. The delivery record is persisted idempotently (Fase C):
    repeats without force return the existing row without re-sending;
    force=True re-attempts a failed/disabled/pending delivery and updates
    the SAME row (manual redispatch, no retry daemon). Already
    sent/simulated rows are never re-sent (409).
    """
    alert: Optional[Alert] = None
    if body.alert_id is not None:
        alert_uuid = _validate_uuid(body.alert_id, "alert_id")
        alert = _find_alert_by_id(request, alert_uuid)
        if alert is None:
            # Recovery after restart: the runtime list is empty but the
            # alert row is durable. Rebuild the domain alert preserving
            # its original owner (ownership is never stolen).
            try:
                alert_row = _alert_repo.get_by_id(db, alert_uuid)
            except Exception:
                alert_row = None
            if alert_row is not None:
                alert = Alert(
                    id=alert_row.id,
                    device_id=alert_row.device_id,
                    user_id=alert_row.user_id,
                    type=alert_row.type,
                    message=alert_row.message,
                    criticality=float(alert_row.criticality),
                    acknowledged=bool(alert_row.acknowledged),
                    created_at=alert_row.created_at,
                )

    if alert is None:
        if body.type is not None and body.device_id is not None:
            dev_uuid = _validate_uuid(body.device_id, "device_id")
            usr_uuid = current.id
            alt_uuid = (
                _validate_uuid(body.alert_id, "alert_id")
                if body.alert_id
                else uuid4()
            )
            alert = Alert(
                id=alt_uuid,
                device_id=dev_uuid,
                user_id=usr_uuid,
                type=body.type,
                message=body.message or "Alert triggered",
                criticality=body.criticality if body.criticality is not None else 5.0,
                acknowledged=False,
                created_at=datetime.now(timezone.utc),
            )
            _get_alerts_list(request).append(alert)
        elif body.alert_id is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert not found.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either 'alert_id' or alert details ('device_id', 'type') must be provided.",
            )

    service = _get_notification_service(request)
    try:
        result, persisted = service.process_and_persist(
            alert,
            db,
            recipient=body.recipient,
            message=body.message,
            force=body.force,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Duplicate detection keys on the service's explicit duplicate marker,
    # not on a missing notification: the force-redispatch race returns the
    # fresh attempt (notification + send_result) together with the winner row.
    duplicate = persisted is not None and (result.error or "").startswith("duplicate:")
    redelivered = False

    if duplicate and body.force and persisted is not None:
        # Manual redispatch: a fresh delivery was just attempted (see
        # process_and_persist's IntegrityError path). Only
        # failed/disabled/pending rows adopt the new outcome; already
        # sent/simulated rows are never rewritten nor re-sent.
        fresh_status = (
            result.send_result.status.value
            if result.send_result is not None
            else None
        )
        if str(persisted.status) in REDISPATCHABLE_STATUSES and fresh_status is not None:
            try:
                _notif_repo.update_status(
                    db,
                    persisted,
                    fresh_status,
                    result.send_result.detail if result.send_result else result.error,
                )
                _audit_best_effort(
                    db,
                    actor_id=current.id,
                    action="notification.redispatch",
                    resource=f"notifications/{persisted.id}",
                    new_value={"status": fresh_status},
                )
                redelivered = True
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Notification already delivered or simulated; not re-sent.",
            )

    notifications_list = _get_notifications_list(request)
    if result.notification is not None and not duplicate:
        if all(n.id != result.notification.id for n in notifications_list):
            notifications_list.append(result.notification)
        # TSK-059.5 — audit creation (no previous state exists).
        # This commit also durably stores the flushed delivery row.
        _audit_best_effort(
            db,
            actor_id=current.id,
            action="notification.process",
            resource=f"notifications/{result.notification.id}",
        )

    if duplicate and persisted is not None:
        summaries = _alert_summaries(db, {persisted.alert_id})
        serialized_notif: Any = _serialize_persistent(
            persisted, summaries.get(persisted.alert_id)
        )
        success = str(persisted.status) == NotificationStatus.SENT.value
    else:
        serialized_notif = (
            _serialize_notification(result.notification, _get_alerts_list(request))
            if result.notification is not None
            else None
        )
        success = result.succeeded

    send_result_data = None
    if result.send_result is not None:
        send_result_data = {
            "notification_id": str(result.send_result.notification_id),
            "channel": (
                result.send_result.channel.value
                if hasattr(result.send_result.channel, "value")
                else str(result.send_result.channel)
            ),
            "status": (
                result.send_result.status.value
                if hasattr(result.send_result.status, "value")
                else str(result.send_result.status)
            ),
            "detail": result.send_result.detail,
        }

    return {
        "success": success,
        "alert_id": str(result.alert_id),
        "notification": serialized_notif,
        "send_result": send_result_data,
        "error": result.error,
        "duplicate": duplicate,
        "redelivered": redelivered,
        "persisted": persisted is not None,
    }
