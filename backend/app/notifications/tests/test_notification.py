from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.events.domain import Alert
from app.notifications.domain import (
    Notification,
    NotificationChannel,
    NotificationStatus,
)


def make_alert() -> Alert:
    return Alert(
        id=uuid4(),
        device_id=uuid4(),
        user_id=uuid4(),
        type="TEMPERATURE_EXCEEDED",
        message="Temperature exceeded",
        criticality=8.0,
        acknowledged=False,
        created_at=datetime.now(timezone.utc),
    )


def test_notification_preserves_alert_traceability():
    alert = make_alert()

    notification = Notification.from_alert(
        alert,
        channel=NotificationChannel.DASHBOARD,
    )

    assert notification.alert_id == alert.id
    assert notification.alert is alert
    assert notification.channel is NotificationChannel.DASHBOARD
    assert notification.status is NotificationStatus.PENDING
    assert isinstance(notification.notification_date, datetime)


@pytest.mark.parametrize("channel", ("email", "sms", "push", "dashboard"))
def test_notification_accepts_supported_channels(channel):
    notification = Notification(
        id=uuid4(),
        alert_id=uuid4(),
        channel=channel,
        status="pending",
        notification_date=datetime.now(timezone.utc),
    )

    assert notification.channel.value == channel


@pytest.mark.parametrize("status", ("pending", "sent", "failed"))
def test_notification_accepts_delivery_states(status):
    notification = Notification(
        id=uuid4(),
        alert_id=uuid4(),
        channel=NotificationChannel.EMAIL,
        status=status,
        notification_date=datetime.now(timezone.utc),
    )

    assert notification.status.value == status


def test_notification_rejects_invalid_channel():
    with pytest.raises(ValueError, match="channel"):
        Notification(
            id=uuid4(),
            alert_id=uuid4(),
            channel="whatsapp",
            status="pending",
            notification_date=datetime.now(timezone.utc),
        )


def test_notification_rejects_invalid_status():
    with pytest.raises(ValueError, match="status"):
        Notification(
            id=uuid4(),
            alert_id=uuid4(),
            channel="email",
            status="delivered",
            notification_date=datetime.now(timezone.utc),
        )


def test_notification_rejects_mismatched_alert_reference():
    alert = make_alert()

    with pytest.raises(ValueError, match="alert_id"):
        Notification(
            id=uuid4(),
            alert_id=uuid4(),
            channel="dashboard",
            status="pending",
            notification_date=datetime.now(timezone.utc),
            alert=alert,
        )


def test_from_alert_requires_alert_domain_entity():
    with pytest.raises(TypeError, match="Alert"):
        Notification.from_alert(
            alert="not-an-alert",
            channel="dashboard",
        )
