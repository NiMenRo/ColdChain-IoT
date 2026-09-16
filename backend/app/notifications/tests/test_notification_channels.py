from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.events.domain import Alert
from app.notifications.application import (
    DashboardNotificationChannel,
    EmailNotificationChannel,
    NotificationChannelRegistry,
    NotificationManager,
    NotificationSendRequest,
    PushNotificationChannel,
    SMSNotificationChannel,
)
from app.notifications.domain import NotificationChannel, NotificationStatus


def make_notification(channel: str = "dashboard"):
    alert = Alert(
        id=uuid4(),
        device_id=uuid4(),
        user_id=uuid4(),
        type="TEMPERATURE_EXCEEDED",
        message="Temperature exceeded",
        criticality=8.0,
        acknowledged=False,
        created_at=datetime.now(timezone.utc),
    )
    return NotificationManager(default_channel=channel).prepare(alert)


@pytest.mark.parametrize(
    ("sender", "channel"),
    (
        (DashboardNotificationChannel(), NotificationChannel.DASHBOARD),
        (EmailNotificationChannel(), NotificationChannel.EMAIL),
        (SMSNotificationChannel(), NotificationChannel.SMS),
        (PushNotificationChannel(), NotificationChannel.PUSH),
    ),
)
def test_each_channel_processes_a_request(sender, channel):
    notification = make_notification(channel.value)
    request = NotificationSendRequest(notification, "recipient", "Alert message")

    result = sender.send(request)

    assert result.status is NotificationStatus.SENT
    assert result.channel is channel
    assert result.notification_id == notification.id
    assert notification.status is NotificationStatus.SENT
    assert len(sender.deliveries) == 1


def test_registry_selects_sender_from_notification_channel():
    registry = NotificationChannelRegistry()
    notification = make_notification("sms")

    result = registry.send(
        NotificationSendRequest(notification, "+573000000000", "Power loss")
    )

    assert result.channel is NotificationChannel.SMS
    assert result.status is NotificationStatus.SENT


def test_failed_delivery_is_registered_in_result_and_notification():
    class FailingDashboardChannel(DashboardNotificationChannel):
        def _deliver(self, request):
            raise RuntimeError("transport unavailable")

    notification = make_notification()
    result = FailingDashboardChannel().send(
        NotificationSendRequest(notification, "operator", "Critical alert")
    )

    assert result.status is NotificationStatus.FAILED
    assert "transport unavailable" in result.detail
    assert notification.status is NotificationStatus.FAILED


def test_registry_accepts_new_channel_without_changing_manager():
    custom_deliveries = []
    custom_channel = DashboardNotificationChannel(deliveries=custom_deliveries)
    registry = NotificationChannelRegistry(channels=[custom_channel])
    notification = make_notification("dashboard")

    result = registry.send(NotificationSendRequest(notification, "dashboard", "Alert"))

    assert result.status is NotificationStatus.SENT
    assert len(custom_deliveries) == 1


def test_request_validates_required_delivery_data():
    notification = make_notification()

    with pytest.raises(ValueError):
        NotificationSendRequest(notification, "", "Alert")
    with pytest.raises(ValueError):
        NotificationSendRequest(notification, "recipient", "")
