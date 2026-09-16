from __future__ import annotations

from collections.abc import Mapping

from app.events.domain import Alert
from app.notifications.domain import (
    Notification,
    NotificationChannel,
    NotificationStatus,
)


class NotificationManager:
    """Orchestrates notification preparation without performing delivery.

    ``channel_by_alert_type`` is an optional routing configuration. Alert types
    not present in that mapping use ``default_channel``. Concrete email, SMS,
    push, or dashboard senders are deliberately not dependencies of this
    manager.
    """

    def __init__(
        self,
        default_channel: NotificationChannel | str = NotificationChannel.DASHBOARD,
        channel_by_alert_type: Mapping[str, NotificationChannel | str] | None = None,
    ) -> None:
        self._default_channel = self._normalize_channel(default_channel)
        self._channel_by_alert_type = {
            self._normalize_alert_type(alert_type): self._normalize_channel(channel)
            for alert_type, channel in (channel_by_alert_type or {}).items()
        }

    def select_channel(self, alert: Alert) -> NotificationChannel:
        """Select the configured channel for an alert."""
        self._validate_alert(alert)
        return self._channel_by_alert_type.get(
            self._normalize_alert_type(alert.type),
            self._default_channel,
        )

    def prepare(
        self,
        alert: Alert,
        *,
        status: NotificationStatus | str = NotificationStatus.PENDING,
    ) -> Notification:
        """Create a pending notification request ready for a delivery adapter."""
        self._validate_alert(alert)
        return Notification.from_alert(
            alert=alert,
            channel=self.select_channel(alert),
            status=status,
        )

    def create_notification(
        self,
        alert: Alert,
        *,
        status: NotificationStatus | str = NotificationStatus.PENDING,
    ) -> Notification:
        """Explicit alias for preparing one notification from an alert."""
        return self.prepare(alert, status=status)

    @staticmethod
    def _normalize_channel(
        channel: NotificationChannel | str,
    ) -> NotificationChannel:
        if isinstance(channel, NotificationChannel):
            return channel
        if isinstance(channel, str):
            try:
                return NotificationChannel(channel.strip().lower())
            except ValueError as exc:
                raise ValueError(
                    "channel must be one of email, sms, push, or dashboard"
                ) from exc
        raise TypeError("'channel' must be a NotificationChannel or string")

    @staticmethod
    def _normalize_alert_type(alert_type: str) -> str:
        if not isinstance(alert_type, str) or not alert_type.strip():
            raise ValueError("alert type must be a non-empty string")
        return alert_type.strip().upper()

    @staticmethod
    def _validate_alert(alert: Alert) -> None:
        if not isinstance(alert, Alert):
            raise TypeError("'alert' must be an Alert instance")


__all__ = ["NotificationManager"]
