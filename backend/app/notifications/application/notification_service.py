from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from app.events.domain import Alert
from app.notifications.application.notification_channel import (
    NotificationChannelRegistry,
    NotificationSendRequest,
    NotificationSendResult,
)
from app.notifications.application.notification_manager import NotificationManager
from app.notifications.domain import Notification, NotificationStatus


@dataclass(frozen=True)
class NotificationProcessResult:
    """Traceable outcome linking an alert, notification, and delivery attempt."""

    alert_id: UUID
    notification: Optional[Notification]
    send_result: Optional[NotificationSendResult]
    error: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        """True only when the transport confirmed a REAL delivery (SENT).

        Simulated/disabled outcomes complete processing but never count
        as sent: a simulated row must never be reported as delivered.
        """
        return (
            self.send_result is not None
            and self.send_result.status is NotificationStatus.SENT
            and self.error is None
        )

    @property
    def completed(self) -> bool:
        """True when processing finished without an internal error.

        Covers SENT, SIMULATED, DISABLED and transport FAILED: in all
        these cases the pipeline must continue (no alert is ever lost
        because of a notification outcome).
        """
        return self.send_result is not None and self.error is None


class NotificationService:
    """Coordinates notification preparation and channel execution."""

    def __init__(
        self,
        manager: NotificationManager | None = None,
        channel_registry: NotificationChannelRegistry | None = None,
        recipient_resolver: Callable[[Alert], str] | None = None,
    ) -> None:
        self._manager = manager or NotificationManager()
        self._channel_registry = channel_registry or NotificationChannelRegistry()
        self._recipient_resolver = recipient_resolver or (
            lambda alert: str(alert.user_id)
        )

    def resolve_recipient(self, alert: Alert, override: str | None = None) -> str:
        """Resolve the delivery recipient for an alert (public helper)."""
        self._validate_alert(alert)
        return self._recipient_resolver(alert) if override is None else override

    def resolve_message(self, alert: Alert, override: str | None = None) -> str:
        """Resolve the delivery message for an alert (public helper)."""
        self._validate_alert(alert)
        return alert.message if override is None else override

    def process(
        self,
        alert: Alert,
        *,
        recipient: str | None = None,
        message: str | None = None,
    ) -> NotificationProcessResult:
        """Prepare and deliver one alert through its configured channel.

        The service does not select channels or implement transport behavior;
        those responsibilities remain with ``NotificationManager`` and the
        registered channel adapters. Channel/transport failures never
        propagate: they are recorded as FAILED (or SIMULATED/DISABLED by
        the adapter) so callers — in particular the acquisition pipeline —
        never lose an alert because of a notification outcome.
        """
        self._validate_alert(alert)
        notification: Notification | None = None
        try:
            notification = self._manager.prepare(alert)
            request = NotificationSendRequest(
                notification=notification,
                recipient=self.resolve_recipient(alert, recipient),
                message=self.resolve_message(alert, message),
            )
            send_result = self._channel_registry.send(request)
            return NotificationProcessResult(
                alert_id=alert.id,
                notification=notification,
                send_result=send_result,
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            if notification is not None:
                notification.status = NotificationStatus.FAILED
            return NotificationProcessResult(
                alert_id=alert.id,
                notification=notification,
                send_result=None,
                error=str(exc),
            )

    def process_and_persist(
        self,
        alert: Alert,
        db,
        *,
        recipient: str | None = None,
        message: str | None = None,
        user_id: UUID | None = None,
        force: bool = False,
    ):
        """Process one alert and persist the delivery record idempotently.

        Session/transaction contract (explicit):
        - ``db`` is a caller-owned ``Session``. This method only flushes;
          commit/rollback of the outer transaction belongs to the caller,
          EXCEPT on a unique-race ``IntegrityError`` (concurrent duplicate),
          where it rolls back its own flush and returns the existing row.
        - Callers must isolate notification persistence in its own
          transaction (as the acquisition pipeline does), so a rollback
          here can never discard alerts or readings.
        - Channel/send failures never propagate (see :meth:`process`).
          Database lookup failures DO propagate: they signal an
          infrastructure problem the caller must handle.
        - Idempotency: unless ``force=True``, an existing row for
          ``(alert_id, channel, recipient)`` is returned without
          re-sending (no duplicate deliveries on reprocessing/retries).

        Returns ``(result, orm_row_or_existing_or_None)``.
        """
        from sqlalchemy.exc import IntegrityError

        from app.database.infrastructure.repositories import NotificationRepository

        self._validate_alert(alert)
        repo = NotificationRepository()
        owner = user_id if user_id is not None else alert.user_id
        if not isinstance(owner, UUID):
            return (
                NotificationProcessResult(
                    alert_id=alert.id,
                    notification=None,
                    send_result=None,
                    error="'user_id' must be a UUID",
                ),
                None,
            )
        try:
            channel = self._manager.select_channel(alert)
        except (TypeError, ValueError) as exc:
            return (
                NotificationProcessResult(
                    alert_id=alert.id,
                    notification=None,
                    send_result=None,
                    error=str(exc),
                ),
                None,
            )
        resolved_recipient = self.resolve_recipient(alert, recipient)
        resolved_message = self.resolve_message(alert, message)
        if not force:
            existing = repo.find_duplicate(
                db, alert.id, channel.value, resolved_recipient
            )
            if existing is not None:
                return (
                    NotificationProcessResult(
                        alert_id=alert.id,
                        notification=None,
                        send_result=None,
                        error="duplicate: notification already recorded",
                    ),
                    existing,
                )
        result = self.process(alert, recipient=recipient, message=message)
        if result.notification is None:
            return result, None
        try:
            row = repo.create(
                db,
                alert_id=alert.id,
                user_id=owner,
                channel=result.notification.channel.value,
                status=result.notification.status.value,
                recipient=resolved_recipient,
                message=resolved_message,
                detail=(
                    result.send_result.detail
                    if result.send_result is not None
                    else result.error
                ),
                notification_date=result.notification.notification_date,
                notification_id=result.notification.id,
            )
        except IntegrityError:
            # Concurrent duplicate won the race: drop only our flush and
            # return the winner. Safe only because callers persist
            # notifications in an isolated transaction.
            db.rollback()
            existing = repo.find_duplicate(
                db, alert.id, channel.value, resolved_recipient
            )
            return (
                NotificationProcessResult(
                    alert_id=alert.id,
                    notification=result.notification,
                    send_result=result.send_result,
                    error="duplicate: notification already recorded",
                ),
                existing,
            )
        return result, row

    def notify(
        self,
        alert: Alert,
        *,
        recipient: str | None = None,
        message: str | None = None,
    ) -> NotificationProcessResult:
        """Alias for processing one notification request."""
        return self.process(alert, recipient=recipient, message=message)

    @staticmethod
    def _validate_alert(alert: Alert) -> None:
        if not isinstance(alert, Alert):
            raise TypeError("'alert' must be an Alert instance")


__all__ = ["NotificationProcessResult", "NotificationService"]
