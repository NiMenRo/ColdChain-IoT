from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.events.domain import Alert
from app.notifications.application import NotificationManager
from app.notifications.domain import NotificationChannel, NotificationStatus


def make_alert(alert_type: str = "TEMPERATURE_EXCEEDED") -> Alert:
    return Alert(
        id=uuid4(),
        device_id=uuid4(),
        user_id=uuid4(),
        type=alert_type,
        message="Cold-chain condition breached",
        criticality=8.0,
        acknowledged=False,
        created_at=datetime.now(timezone.utc),
    )


def test_manager_prepares_traceable_notification():
    alert = make_alert()
    manager = NotificationManager(default_channel="dashboard")

    notification = manager.prepare(alert)

    assert notification.alert_id == alert.id
    assert notification.alert is alert
    assert notification.channel is NotificationChannel.DASHBOARD
    assert notification.status is NotificationStatus.PENDING


def test_manager_selects_channel_from_alert_type_configuration():
    manager = NotificationManager(
        default_channel="dashboard",
        channel_by_alert_type={"ENERGY_STATE_ANOMALY": "sms"},
    )

    notification = manager.create_notification(make_alert("ENERGY_STATE_ANOMALY"))

    assert notification.channel is NotificationChannel.SMS


def test_manager_uses_default_for_unconfigured_alert_type():
    manager = NotificationManager(
        default_channel="email",
        channel_by_alert_type={"ENERGY_STATE_ANOMALY": "sms"},
    )

    notification = manager.prepare(make_alert("HUMIDITY_ABOVE_MAX"))

    assert notification.channel is NotificationChannel.EMAIL


def test_manager_can_prepare_requested_delivery_state_without_sending():
    manager = NotificationManager()

    notification = manager.prepare(make_alert(), status="failed")

    assert notification.status is NotificationStatus.FAILED


@pytest.mark.parametrize("invalid_channel", ("whatsapp", "", 10))
def test_manager_rejects_invalid_channel_configuration(invalid_channel):
    with pytest.raises((TypeError, ValueError)):
        NotificationManager(default_channel=invalid_channel)


def test_manager_rejects_non_alert_input():
    manager = NotificationManager()

    with pytest.raises(TypeError, match="Alert"):
        manager.prepare("not-an-alert")
