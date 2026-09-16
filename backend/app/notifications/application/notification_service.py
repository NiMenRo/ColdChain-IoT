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
        return (
            self.send_result is not None
            and self.send_result.status is NotificationStatus.SENT
            and self.error is None
        )


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
        registered channel adapters.
        """
        self._validate_alert(alert)
        notification: Notification | None = None
        try:
            notification = self._manager.prepare(alert)
            resolved_recipient = (
                self._recipient_resolver(alert) if recipient is None else recipient
            )
            resolved_message = alert.message if message is None else message
            request = NotificationSendRequest(
                notification=notification,
                recipient=resolved_recipient,
                message=resolved_message,
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
