"""REST API endpoints for the notification module."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

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
    user_id: Optional[str] = None
    acknowledged: Optional[bool] = True


class UpdateNotificationStatusRequest(BaseModel):
    status: str


class NotificationProcessRequest(BaseModel):
    alert_id: Optional[str] = None
    recipient: Optional[str] = None
    message: Optional[str] = None
    device_id: Optional[str] = None
    user_id: Optional[str] = None
    type: Optional[str] = None
    criticality: Optional[float] = None


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
# Endpoints: Single Notification
# ---------------------------------------------------------------------------

@router.get("/{notification_id}")
def get_notification_by_id(request: Request, notification_id: str):
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
def get_notification_status(request: Request, notification_id: str):
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
            notif.status = NotificationStatus(raw_status)
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

def _perform_acknowledgement(
    request: Request,
    alert_uuid: UUID,
    user_id_str: Optional[str] = None,
) -> dict[str, Any]:
    alert = _find_alert_by_id(request, alert_uuid)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found.",
        )

    parsed_user_id: Optional[UUID] = None
    if user_id_str is not None:
        parsed_user_id = _validate_uuid(user_id_str, "user_id")

    ack_service = _get_ack_service(request)
    updated_alert = ack_service.acknowledge(alert, user_id=parsed_user_id)

    # Ensure any notifications linking to this alert are in sync
    notifications_list = _get_notifications_list(request)
    for notif in notifications_list:
        if notif.alert_id == alert_uuid and notif.alert is not None:
            notif.alert.acknowledged = True

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
):
    """Register acknowledgement of an Alert by a user."""
    alert_uuid = _validate_uuid(alert_id, "alert_id")
    user_id = body.user_id if body else None
    return _perform_acknowledgement(request, alert_uuid, user_id)


@router.post("/acknowledge")
def acknowledge_alert_body(
    request: Request,
    body: dict[str, Any],
):
    """Register acknowledgement where alert_id is provided in request body."""
    raw_alert_id = body.get("alert_id")
    if not raw_alert_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'alert_id' must be provided in request body.",
        )
    alert_uuid = _validate_uuid(str(raw_alert_id), "alert_id")
    user_id = body.get("user_id")
    return _perform_acknowledgement(request, alert_uuid, str(user_id) if user_id else None)


@router.post("/{notification_id}/acknowledge")
def acknowledge_via_notification(
    request: Request,
    notification_id: str,
    body: Optional[AcknowledgeAlertRequest] = None,
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
    ack_result = _perform_acknowledgement(request, target_notif.alert_id, user_id)
    if target_notif.alert is not None:
        target_notif.alert.acknowledged = True

    serialized_notif = _serialize_notification(target_notif, _get_alerts_list(request))
    return {
        **ack_result,
        "notification": serialized_notif,
    }


@router.get("/alerts/{alert_id}")
@router.get("/alerts/{alert_id}/status")
def get_alert_status(request: Request, alert_id: str):
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
):
    """Process an alert through NotificationService to generate and send a notification."""
    alert: Optional[Alert] = None
    if body.alert_id is not None:
        alert_uuid = _validate_uuid(body.alert_id, "alert_id")
        alert = _find_alert_by_id(request, alert_uuid)

    if alert is None:
        if body.type is not None and body.device_id is not None:
            dev_uuid = _validate_uuid(body.device_id, "device_id")
            usr_uuid = (
                _validate_uuid(body.user_id, "user_id") if body.user_id else uuid4()
            )
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
        result = service.process(
            alert,
            recipient=body.recipient,
            message=body.message,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    notifications_list = _get_notifications_list(request)
    if result.notification is not None:
        notifications_list.append(result.notification)

    serialized_notif = (
        _serialize_notification(result.notification, _get_alerts_list(request))
        if result.notification is not None
        else None
    )

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
        "success": result.succeeded,
        "alert_id": str(result.alert_id),
        "notification": serialized_notif,
        "send_result": send_result_data,
        "error": result.error,
    }
