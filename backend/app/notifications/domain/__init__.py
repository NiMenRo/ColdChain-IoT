from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from app.events.domain import Alert


class NotificationChannel(str, Enum):
    """Channels supported by the notification domain."""

    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    DASHBOARD = "dashboard"


class NotificationStatus(str, Enum):
    """Lifecycle state of a notification delivery record."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


@dataclass
class Notification:
    """A notification record associated with one originating alert.

    This entity records delivery information only. Channel-specific sending is
    intentionally outside the domain model and belongs to a later application
    service.
    """

    id: UUID
    alert_id: UUID
    channel: NotificationChannel
    status: NotificationStatus
    notification_date: datetime
    alert: Optional[Alert] = None

    def __post_init__(self) -> None:
        self._validate_id()
        self._validate_alert_id()
        self._normalize_channel()
        self._normalize_status()
        self._validate_notification_date()
        self._validate_alert_reference()

    @classmethod
    def from_alert(
        cls,
        alert: Alert,
        channel: NotificationChannel | str,
        status: NotificationStatus | str = NotificationStatus.PENDING,
        notification_date: datetime | None = None,
    ) -> "Notification":
        """Create a traceable notification from an existing alert."""
        if not isinstance(alert, Alert):
            raise TypeError("'alert' must be an Alert instance")
        return cls(
            id=uuid4(),
            alert_id=alert.id,
            channel=channel,
            status=status,
            notification_date=notification_date or datetime.now(timezone.utc),
            alert=alert,
        )

    def _validate_id(self) -> None:
        if not isinstance(self.id, UUID):
            raise TypeError("'id' must be a UUID instance")

    def _validate_alert_id(self) -> None:
        if not isinstance(self.alert_id, UUID):
            raise TypeError("'alert_id' must be a UUID instance")

    def _normalize_channel(self) -> None:
        if isinstance(self.channel, str):
            try:
                self.channel = NotificationChannel(self.channel.strip().lower())
            except ValueError as exc:
                raise ValueError(
                    "channel must be one of email, sms, push, or dashboard"
                ) from exc
        elif not isinstance(self.channel, NotificationChannel):
            raise TypeError("'channel' must be a NotificationChannel or string")

    def _normalize_status(self) -> None:
        if isinstance(self.status, str):
            try:
                self.status = NotificationStatus(self.status.strip().lower())
            except ValueError as exc:
                raise ValueError(
                    "status must be one of pending, sent, or failed"
                ) from exc
        elif not isinstance(self.status, NotificationStatus):
            raise TypeError("'status' must be a NotificationStatus or string")

    def _validate_notification_date(self) -> None:
        if not isinstance(self.notification_date, datetime):
            raise TypeError("'notification_date' must be a datetime instance")

    def _validate_alert_reference(self) -> None:
        if self.alert is not None:
            if not isinstance(self.alert, Alert):
                raise TypeError("'alert' must be an Alert instance")
            if self.alert.id != self.alert_id:
                raise ValueError("'alert.id' must match 'alert_id'")


__all__ = [
    "Notification",
    "NotificationChannel",
    "NotificationStatus",
]