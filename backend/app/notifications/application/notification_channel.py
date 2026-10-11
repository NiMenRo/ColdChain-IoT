from __future__ import annotations

import logging
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any
from uuid import UUID, uuid4

from app.notifications.application.channel_config import (
    PushConfig,
    SmsConfig,
    SmtpConfig,
)
from app.notifications.domain import Notification, NotificationChannel, NotificationStatus

logger = logging.getLogger(__name__)


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


def _outcome(
    request: NotificationSendRequest,
    channel: NotificationChannel,
    status: NotificationStatus,
    detail: str,
) -> NotificationSendResult:
    request.notification.status = status
    return NotificationSendResult(
        attempt_id=uuid4(),
        notification_id=request.notification.id,
        channel=channel,
        status=status,
        attempted_at=datetime.now(timezone.utc),
        detail=detail,
    )


class SmtpEmailChannel(NotificationChannelSender):
    """Optional real-SMTP email adapter.

    When ``SmtpConfig`` is disabled or incomplete the adapter returns
    ``DISABLED`` without touching the network. Successful SMTP delivery
    returns ``SENT``; transport errors return ``FAILED``. Secrets are
    never included in results, logs, or ``detail`` strings.
    """

    channel = NotificationChannel.EMAIL

    def __init__(self, config: SmtpConfig | None = None) -> None:
        self._config = config or SmtpConfig.from_env()

    def _deliver(self, request: NotificationSendRequest) -> str:
        # Unused: send() is overridden to express DISABLED/FAILED/SENT.
        raise NotImplementedError

    def send(self, request: NotificationSendRequest) -> NotificationSendResult:
        if not isinstance(request, NotificationSendRequest):
            raise TypeError("'request' must be a NotificationSendRequest instance")
        if not self._config.enabled or not self._config.is_configured:
            return _outcome(
                request,
                self.channel,
                NotificationStatus.DISABLED,
                "SMTP email disabled or not configured; no delivery attempted",
            )
        if "@" not in request.recipient:
            return _outcome(
                request,
                self.channel,
                NotificationStatus.FAILED,
                f"invalid email recipient '{request.recipient}'",
            )
        try:
            self._send_mail(request.recipient, request.message)
        except Exception as exc:
            logger.warning("SMTP email delivery failed: %s", exc)
            return _outcome(
                request, self.channel, NotificationStatus.FAILED, f"SMTP error: {exc}"
            )
        return _outcome(
            request,
            self.channel,
            NotificationStatus.SENT,
            f"email delivered via SMTP {self._config.host}:{self._config.port}",
        )

    def _send_mail(self, recipient: str, message: str) -> None:
        msg = EmailMessage()
        msg["From"] = self._config.from_addr
        msg["To"] = recipient
        msg["Subject"] = "ColdChain-IoT alert notification"
        msg.set_content(message)
        with smtplib.SMTP(
            self._config.host, self._config.port,
            timeout=self._config.timeout_seconds,
        ) as client:
            if self._config.use_tls:
                client.starttls()
            if self._config.username:
                # Password goes only to the transport, never to logs/results.
                client.login(self._config.username, self._config.password)
            client.send_message(msg)


class LoggingSmsChannel(NotificationChannelSender):
    """Simulated-SMS adapter.

    This channel NEVER performs a real send: deliveries are recorded in
    ``deliveries`` and in the logs, and the result is always ``SIMULATED``
    (or ``DISABLED`` when simulation is switched off). A simulated row
    must never be reported as sent.
    """

    channel = NotificationChannel.SMS

    def __init__(
        self,
        config: SmsConfig | None = None,
        *,
        deliveries: list[dict[str, Any]] | None = None,
    ) -> None:
        self._config = config or SmsConfig.from_env()
        self.deliveries = deliveries if deliveries is not None else []

    def _deliver(self, request: NotificationSendRequest) -> str:
        # Unused: send() is overridden to express SIMULATED/DISABLED.
        raise NotImplementedError

    def send(self, request: NotificationSendRequest) -> NotificationSendResult:
        if not isinstance(request, NotificationSendRequest):
            raise TypeError("'request' must be a NotificationSendRequest instance")
        if not self._config.simulated:
            return _outcome(
                request,
                self.channel,
                NotificationStatus.DISABLED,
                "SMS simulation disabled; no delivery attempted",
            )
        entry = {
            "notification_id": request.notification.id,
            "recipient": request.recipient,
            "message": request.message,
            "channel": self.channel.value,
            "simulated": True,
        }
        self.deliveries.append(entry)
        logger.info(
            "SMS simulated to %s for notification %s; no real delivery performed",
            request.recipient,
            request.notification.id,
        )
        return _outcome(
            request,
            self.channel,
            NotificationStatus.SIMULATED,
            f"SMS simulated to {request.recipient}; no real delivery performed",
        )


class DecoupledPushChannel(NotificationChannelSender):
    """Decoupled push adapter (simulation/disabled only).

    Web Push is NOT implemented in this phase: there is no service worker,
    no subscription storage, and no FCM/VAPID transport. With
    ``PUSH_ENABLED=true`` deliveries are recorded as ``SIMULATED``;
    otherwise ``DISABLED``. Never ``SENT``.
    """

    channel = NotificationChannel.PUSH

    def __init__(
        self,
        config: PushConfig | None = None,
        *,
        deliveries: list[dict[str, Any]] | None = None,
    ) -> None:
        self._config = config or PushConfig.from_env()
        self.deliveries = deliveries if deliveries is not None else []

    def _deliver(self, request: NotificationSendRequest) -> str:
        # Unused: send() is overridden to express SIMULATED/DISABLED.
        raise NotImplementedError

    def send(self, request: NotificationSendRequest) -> NotificationSendResult:
        if not isinstance(request, NotificationSendRequest):
            raise TypeError("'request' must be a NotificationSendRequest instance")
        if not self._config.enabled:
            return _outcome(
                request,
                self.channel,
                NotificationStatus.DISABLED,
                "push adapter decoupled (Web Push not implemented); "
                "no delivery attempted",
            )
        self.deliveries.append(
            {
                "notification_id": request.notification.id,
                "recipient": request.recipient,
                "message": request.message,
                "channel": self.channel.value,
                "simulated": True,
            }
        )
        logger.info(
            "Push simulated to %s for notification %s; no real delivery performed",
            request.recipient,
            request.notification.id,
        )
        return _outcome(
            request,
            self.channel,
            NotificationStatus.SIMULATED,
            "push simulated (adapter decoupled); no real delivery performed",
        )


def production_channels() -> list[NotificationChannelSender]:
    """Channel set wired in production from environment configuration.

    Dashboard stays in-app (real ``SENT``); email uses optional real SMTP
    (``SENT``/``FAILED``/``DISABLED``); SMS is simulated; push is
    decoupled. Local runs without credentials work: nothing blocks and
    nothing claims a real delivery it did not perform.
    """
    return [
        DashboardNotificationChannel(),
        SmtpEmailChannel(SmtpConfig.from_env()),
        LoggingSmsChannel(SmsConfig.from_env()),
        DecoupledPushChannel(PushConfig.from_env()),
    ]


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
    "DecoupledPushChannel",
    "EmailNotificationChannel",
    "InMemoryNotificationChannel",
    "LoggingSmsChannel",
    "NotificationChannelRegistry",
    "NotificationChannelSender",
    "NotificationSendRequest",
    "NotificationSendResult",
    "PushNotificationChannel",
    "SMSNotificationChannel",
    "SmtpEmailChannel",
    "production_channels",
]
