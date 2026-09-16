from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.events.domain import Alert
from app.notifications.application import (
    DashboardNotificationChannel,
    NotificationChannelRegistry,
    NotificationManager,
    NotificationService,
)
from app.notifications.domain import NotificationChannel, NotificationStatus


def make_alert(alert_type: str = "TEMPERATURE_EXCEEDED") -> Alert:
    return Alert(
        id=uuid4(),
        device_id=uuid4(),
        user_id=uuid4(),
        type=alert_type,
        message="Temperature exceeded",
        criticality=8.0,
        acknowledged=False,
        created_at=datetime.now(timezone.utc),
    )


def test_service_processes_alert_and_preserves_traceability():
    deliveries = []
    registry = NotificationChannelRegistry(
        channels=[DashboardNotificationChannel(deliveries=deliveries)]
    )
    service = NotificationService(
        manager=NotificationManager(default_channel="dashboard"),
        channel_registry=registry,
        recipient_resolver=lambda alert: "operator-dashboard",
    )
    alert = make_alert()

    result = service.process(alert)

    assert result.succeeded is True
    assert result.alert_id == alert.id
    assert result.notification is not None
    assert result.notification.alert_id == alert.id
    assert result.notification.alert is alert
    assert result.notification.status is NotificationStatus.SENT
    assert result.send_result is not None
    assert result.send_result.notification_id == result.notification.id
    assert deliveries[0]["recipient"] == "operator-dashboard"


def test_service_delegates_channel_selection_to_manager():
    deliveries = []
    registry = NotificationChannelRegistry(
        channels=[
            DashboardNotificationChannel(deliveries=deliveries),
        ]
    )
    service = NotificationService(
        manager=NotificationManager(
            default_channel="dashboard",
            channel_by_alert_type={"ENERGY_STATE_ANOMALY": "dashboard"},
        ),
        channel_registry=registry,
    )

    result = service.notify(
        make_alert("ENERGY_STATE_ANOMALY"),
        recipient="system",
        message="Power loss",
    )

    assert result.succeeded is True
    assert deliveries[0]["message"] == "Power loss"


def test_service_returns_failed_result_when_transport_fails():
    class FailingDashboardChannel(DashboardNotificationChannel):
        def _deliver(self, request):
            raise RuntimeError("transport unavailable")

    service = NotificationService(
        manager=NotificationManager(default_channel="dashboard"),
        channel_registry=NotificationChannelRegistry(
            channels=[FailingDashboardChannel()]
        ),
    )

    result = service.process(make_alert())

    assert result.succeeded is False
    assert result.error is None
    assert result.send_result is not None
    assert result.send_result.status is NotificationStatus.FAILED
    assert result.notification is not None
    assert result.notification.status is NotificationStatus.FAILED


def test_service_controls_invalid_recipient_without_losing_notification_trace():
    service = NotificationService(
        manager=NotificationManager(default_channel="dashboard"),
        channel_registry=NotificationChannelRegistry(
            channels=[DashboardNotificationChannel()]
        ),
    )

    result = service.process(make_alert(), recipient="")

    assert result.succeeded is False
    assert result.error is not None
    assert result.send_result is None
    assert result.notification is not None
    assert result.notification.status is NotificationStatus.FAILED


def test_service_rejects_non_alert_input():
    service = NotificationService()

    with pytest.raises(TypeError, match="Alert"):
        service.process("not-an-alert")
