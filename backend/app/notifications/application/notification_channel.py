from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.notifications.domain import Notification, NotificationChannel, NotificationStatus


@dataclass(frozen=True)
class NotificationSendRequest:
    """Channel-independent data required for one delivery attempt."""

    notification: Notification
    recipient: str
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.notification, Notification):
            raise TypeError("'notification' must be a Notification instance")
        if not isinstance(self.recipient, str) or not self.recipient.strip():
            raise ValueError("'recipient' must be a non-empty string")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("'message' must be a non-empty string")


@dataclass(frozen=True)
class NotificationSendResult:
    """Outcome of a channel delivery attempt."""

    attempt_id: UUID
    notification_id: UUID
    channel: NotificationChannel
    status: NotificationStatus
    attempted_at: datetime
    detail: str


class NotificationChannelSender(ABC):
    """Contract implemented independently by every notification channel."""

    channel: NotificationChannel

    def send(self, request: NotificationSendRequest) -> NotificationSendResult:
        if not isinstance(request, NotificationSendRequest):
            raise TypeError("'request' must be a NotificationSendRequest instance")

        attempted_at = datetime.now(timezone.utc)
        try:
            detail = self._deliver(request)
        except Exception as exc:
            request.notification.status = NotificationStatus.FAILED
            return NotificationSendResult(
                attempt_id=uuid4(),
                notification_id=request.notification.id,
                channel=self.channel,
                status=NotificationStatus.FAILED,
                attempted_at=attempted_at,
                detail=str(exc),
            )

        request.notification.status = NotificationStatus.SENT
        return NotificationSendResult(
            attempt_id=uuid4(),
            notification_id=request.notification.id,
            channel=self.channel,
            status=NotificationStatus.SENT,
            attempted_at=attempted_at,
            detail=detail,
        )

    @abstractmethod
    def _deliver(self, request: NotificationSendRequest) -> str:
        """Perform the channel-specific delivery operation."""
        raise NotImplementedError


class InMemoryNotificationChannel(NotificationChannelSender):
    """Prototype transport that records successful deliveries in memory."""

    def __init__(
        self,
        channel: NotificationChannel,
        *,
        deliveries: list[dict[str, Any]] | None = None,
    ) -> None:
        self.channel = channel
        self.deliveries = deliveries if deliveries is not None else []

    def _deliver(self, request: NotificationSendRequest) -> str:
        self.deliveries.append(
            {
                "notification_id": request.notification.id,
                "recipient": request.recipient,
                "message": request.message,
                "channel": self.channel.value,
            }
        )
        return f"{self.channel.value} delivery recorded"


class DashboardNotificationChannel(InMemoryNotificationChannel):
    def __init__(self, *, deliveries: list[dict[str, Any]] | None = None) -> None:
        super().__init__(NotificationChannel.DASHBOARD, deliveries=deliveries)


class EmailNotificationChannel(InMemoryNotificationChannel):
    def __init__(self, *, deliveries: list[dict[str, Any]] | None = None) -> None:
        super().__init__(NotificationChannel.EMAIL, deliveries=deliveries)


class SMSNotificationChannel(InMemoryNotificationChannel):
    def __init__(self, *, deliveries: list[dict[str, Any]] | None = None) -> None:
        super().__init__(NotificationChannel.SMS, deliveries=deliveries)


class PushNotificationChannel(InMemoryNotificationChannel):
    def __init__(self, *, deliveries: list[dict[str, Any]] | None = None) -> None:
        super().__init__(NotificationChannel.PUSH, deliveries=deliveries)


class NotificationChannelRegistry:
    """Resolves a notification channel without coupling callers to adapters."""

    def __init__(self, channels: list[NotificationChannelSender] | None = None) -> None:
        self._channels: dict[NotificationChannel, NotificationChannelSender] = {}
        for channel in channels or self.default_channels():
            self.register(channel)

    @staticmethod
    def default_channels() -> list[NotificationChannelSender]:
        return [
            DashboardNotificationChannel(),
            EmailNotificationChannel(),
            SMSNotificationChannel(),
            PushNotificationChannel(),
        ]

    def register(self, channel: NotificationChannelSender) -> None:
        if not isinstance(channel, NotificationChannelSender):
            raise TypeError("'channel' must implement NotificationChannelSender")
        self._channels[channel.channel] = channel

    def get(self, channel: NotificationChannel | str) -> NotificationChannelSender:
        normalized = (
            channel
            if isinstance(channel, NotificationChannel)
            else NotificationChannel(channel.strip().lower())
        )
        try:
            return self._channels[normalized]
        except KeyError as exc:
            raise ValueError(f"No sender registered for channel '{normalized.value}'") from exc

    def send(self, request: NotificationSendRequest) -> NotificationSendResult:
        return self.get(request.notification.channel).send(request)


__all__ = [
    "DashboardNotificationChannel",
    "EmailNotificationChannel",
    "InMemoryNotificationChannel",
    "NotificationChannelRegistry",
    "NotificationChannelSender",
    "NotificationSendRequest",
    "NotificationSendResult",
    "PushNotificationChannel",
    "SMSNotificationChannel",
]
