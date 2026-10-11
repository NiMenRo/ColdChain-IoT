"""Fase A/B — persistence, channels, idempotency, pipeline isolation.

Covers: NotificationORM + migration-shaped schema (via Base.metadata),
User.phone, extended statuses, SMTP-optional/SMS-simulated/push-decoupled
adapters, NotificationRepository idempotency + read helpers, and
NotificationService.process_and_persist transaction contract.
"""

from __future__ import annotations

import os
import smtplib
import uuid
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.infrastructure.base import Base
from app.database.infrastructure.models import (
    AlertORM,
    DeviceORM,
    NotificationORM,
    UserORM,
)
from app.database.infrastructure.repositories import NotificationRepository
from app.events.domain import Alert
from app.notifications.application import (
    DashboardNotificationChannel,
    DecoupledPushChannel,
    LoggingSmsChannel,
    NotificationChannelRegistry,
    NotificationManager,
    NotificationSendRequest,
    NotificationService,
    SmtpEmailChannel,
)
from app.notifications.application.channel_config import (
    PushConfig,
    SmsConfig,
    SmtpConfig,
)
from app.notifications.domain import (
    Notification,
    NotificationChannel,
    NotificationStatus,
)

_CHANNEL_ENV_VARS = (
    "SMTP_ENABLED", "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD",
    "SMTP_FROM", "SMTP_TLS", "SMTP_TIMEOUT_SECONDS", "SMS_SIMULATED",
    "PUSH_ENABLED",
)


@pytest.fixture()
def clean_env(monkeypatch):
    for var in _CHANNEL_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, connection_record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    session = session_factory()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _seed_owner(db, *, phone=None):
    user = UserORM(
        name="Owner", email=f"owner-{uuid4().hex[:8]}@example.com",
        password_hash="hash", role="operador", phone=phone,
    )
    db.add(user)
    db.flush()
    device = DeviceORM(
        code=f"CAVA-{uuid4().hex[:6]}", name="Cava", location="Lab",
        device_type="cold_room", status="active",
    )
    db.add(device)
    db.flush()
    alert = AlertORM(
        device_id=device.id, user_id=user.id, type="TEMPERATURE_EXCEEDED",
        message="Too warm", criticality=8.0, acknowledged=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(alert)
    db.flush()
    return user, device, alert


def _domain_alert(user_id, device_id=None):
    return Alert(
        id=uuid4(), device_id=device_id or uuid4(), user_id=user_id,
        type="TEMPERATURE_EXCEEDED", message="Too warm", criticality=8.0,
        acknowledged=False, created_at=datetime.now(timezone.utc),
    )


def _request(channel="dashboard", recipient="recipient"):
    alert = _domain_alert(uuid4())
    notification = NotificationManager(default_channel=channel).prepare(alert)
    return NotificationSendRequest(notification, recipient, "Alert message")


# --- schema / repository -----------------------------------------------------

def test_notifications_table_and_user_phone_exist(db):
    assert "notifications" in Base.metadata.tables
    assert "phone" in UserORM.__table__.c
    assert "is_read" in NotificationORM.__table__.c


def test_create_defaults_to_unread(db):
    user, _, alert = _seed_owner(db)
    row = NotificationRepository().create(
        db, alert_id=alert.id, user_id=user.id, channel="dashboard",
        status="pending", recipient="operator", message="Too warm",
    )
    assert row.is_read is False
    assert row.read_at is None
    assert row.status == "pending"


def test_create_rejects_invalid_channel_status_recipient(db):
    user, _, alert = _seed_owner(db)
    repo = NotificationRepository()
    with pytest.raises(ValueError, match="channel"):
        repo.create(db, alert_id=alert.id, user_id=user.id, channel="whatsapp",
                    status="pending", recipient="r", message="m")
    with pytest.raises(ValueError, match="status"):
        repo.create(db, alert_id=alert.id, user_id=user.id, channel="sms",
                    status="delivered", recipient="r", message="m")
    with pytest.raises(ValueError, match="recipient"):
        repo.create(db, alert_id=alert.id, user_id=user.id, channel="sms",
                    status="pending", recipient="  ", message="m")
    with pytest.raises(ValueError, match="message"):
        repo.create(db, alert_id=alert.id, user_id=user.id, channel="sms",
                    status="pending", recipient="r", message="")


def test_unique_alert_channel_recipient_enforced(db):
    user, _, alert = _seed_owner(db)
    repo = NotificationRepository()
    repo.create(db, alert_id=alert.id, user_id=user.id, channel="sms",
                status="simulated", recipient="+57000", message="m")
    db.commit()
    with pytest.raises(IntegrityError):
        repo.create(db, alert_id=alert.id, user_id=user.id, channel="sms",
                    status="simulated", recipient="+57000", message="m")
    db.rollback()
    found = repo.find_duplicate(db, alert.id, "sms", "+57000")
    assert found is not None
    assert repo.find_duplicate(db, alert.id, "sms", "+57001") is None


def test_user_phone_optional(db):
    without, _, _ = _seed_owner(db)
    assert without.phone is None
    with_phone, _, _ = _seed_owner(db, phone="+573000000000")
    assert with_phone.phone == "+573000000000"


def test_count_and_mark_read_are_owner_scoped_and_idempotent(db):
    owner, _, alert = _seed_owner(db)
    other, _, _ = _seed_owner(db)
    repo = NotificationRepository()
    row = repo.create(db, alert_id=alert.id, user_id=owner.id, channel="dashboard",
                      status="sent", recipient="op", message="m")
    db.commit()
    assert repo.count_unread(db, owner.id) == 1
    assert repo.count_unread(db, other.id) == 0
    assert repo.mark_read(db, row.id, other.id) is None  # not the owner
    assert repo.count_unread(db, owner.id) == 1
    marked = repo.mark_read(db, row.id, owner.id)
    assert marked is not None and marked.is_read is True
    assert marked.read_at is not None
    first_read_at = marked.read_at
    again = repo.mark_read(db, row.id, owner.id)
    assert again.read_at == first_read_at  # idempotent, timestamp preserved
    assert repo.count_unread(db, owner.id) == 0
    assert repo.mark_all_read(db, owner.id) == 0


def test_mark_all_read_returns_updated_count(db):
    owner, _, alert = _seed_owner(db)
    repo = NotificationRepository()
    for i in range(3):
        repo.create(db, alert_id=alert.id, user_id=owner.id, channel="dashboard",
                    status="sent", recipient=f"op-{i}", message="m")
    db.commit()
    assert repo.mark_all_read(db, owner.id) == 3
    assert repo.count_unread(db, owner.id) == 0


# --- domain ------------------------------------------------------------------

def test_domain_accepts_simulated_and_disabled():
    for status in ("simulated", "disabled", "pending", "sent", "failed"):
        n = Notification(id=uuid4(), alert_id=uuid4(),
                         channel=NotificationChannel.SMS, status=status,
                         notification_date=datetime.now(timezone.utc))
        assert n.status.value == status


def test_domain_read_state_validation():
    with pytest.raises(ValueError, match="is_read"):
        Notification(id=uuid4(), alert_id=uuid4(),
                     channel=NotificationChannel.DASHBOARD, status="pending",
                     notification_date=datetime.now(timezone.utc),
                     is_read=False, read_at=datetime.now(timezone.utc))
    n = Notification(id=uuid4(), alert_id=uuid4(),
                     channel=NotificationChannel.DASHBOARD, status="pending",
                     notification_date=datetime.now(timezone.utc))
    assert n.is_read is False and n.read_at is None
    n.mark_read()
    assert n.is_read is True and n.read_at is not None


# --- channels ----------------------------------------------------------------

def test_smtp_disabled_without_config_never_sends(clean_env):
    channel = SmtpEmailChannel(SmtpConfig.from_env())
    request = _request("email")
    result = channel.send(request)
    assert result.status is NotificationStatus.DISABLED
    assert request.notification.status is NotificationStatus.DISABLED
    assert "no delivery attempted" in result.detail


def test_smtp_failure_is_failed_not_blocking(clean_env, monkeypatch):
    def _boom(*args, **kwargs):
        raise ConnectionError("gateway unreachable")

    monkeypatch.setattr(smtplib, "SMTP", _boom)
    config = SmtpConfig(enabled=True, host="smtp.example.com", port=587,
                        username="u", password="s3cr3t", from_addr="a@example.com")
    request = _request("email")
    result = SmtpEmailChannel(config).send(request)
    assert result.status is NotificationStatus.FAILED
    assert request.notification.status is NotificationStatus.FAILED
    assert "s3cr3t" not in result.detail  # secrets never leak into detail


def test_smtp_success_marks_sent(clean_env, monkeypatch):
    calls = {}

    class _FakeSMTP:
        def __init__(self, *args, **kwargs):
            calls["init"] = (args, kwargs)

        def starttls(self):
            calls["tls"] = True

        def login(self, username, password):
            calls["login"] = (username, password)

        def send_message(self, msg):
            calls["to"] = msg["To"]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    config = SmtpConfig(enabled=True, host="smtp.example.com", port=587,
                        username="u", password="s3cr3t", from_addr="a@example.com")
    request = _request("email", recipient="operator@example.com")
    result = SmtpEmailChannel(config).send(request)
    assert result.status is NotificationStatus.SENT
    assert request.notification.status is NotificationStatus.SENT
    assert calls["login"] == ("u", "s3cr3t")
    assert "s3cr3t" not in result.detail


def test_smtp_rejects_non_email_recipient(clean_env):
    config = SmtpConfig(enabled=True, host="smtp.example.com", port=587,
                        username="u", password="s3cr3t", from_addr="a@example.com")
    request = _request("email", recipient="not-an-email")
    result = SmtpEmailChannel(config).send(request)
    assert result.status is NotificationStatus.FAILED
    assert request.notification.status is NotificationStatus.FAILED
    assert "invalid email recipient" in result.detail


def test_sms_is_always_simulated_never_sent(clean_env):
    deliveries = []
    channel = LoggingSmsChannel(SmsConfig.from_env(), deliveries=deliveries)
    request = _request("sms")
    result = channel.send(request)
    assert result.status is NotificationStatus.SIMULATED
    assert request.notification.status is NotificationStatus.SIMULATED
    assert "no real delivery" in result.detail
    assert deliveries and deliveries[0]["simulated"] is True


def test_sms_disabled_when_simulation_off():
    channel = LoggingSmsChannel(SmsConfig(simulated=False))
    request = _request("sms")
    result = channel.send(request)
    assert result.status is NotificationStatus.DISABLED
    assert request.notification.status is NotificationStatus.DISABLED


def test_push_decoupled_never_sends(clean_env):
    push_request = _request("push")
    disabled = DecoupledPushChannel(PushConfig.from_env()).send(push_request)
    assert disabled.status is NotificationStatus.DISABLED
    assert push_request.notification.status is NotificationStatus.DISABLED
    push_request2 = _request("push")
    simulated = DecoupledPushChannel(PushConfig(enabled=True)).send(push_request2)
    assert simulated.status is NotificationStatus.SIMULATED
    assert push_request2.notification.status is NotificationStatus.SIMULATED


def test_production_registry_reports_honest_statuses(clean_env):
    from app.notifications.application import production_channels

    registry = NotificationChannelRegistry(channels=production_channels())
    sms_result = registry.send(_request("sms"))
    push_result = registry.send(_request("push"))
    email_result = registry.send(_request("email"))
    assert sms_result.status is NotificationStatus.SIMULATED
    assert push_result.status is NotificationStatus.DISABLED
    assert email_result.status is NotificationStatus.DISABLED
    assert not any(r.status is NotificationStatus.SENT
                   for r in (sms_result, push_result, email_result))


# --- service -----------------------------------------------------------------

def _service_with_dashboard(deliveries):
    registry = NotificationChannelRegistry(
        channels=[DashboardNotificationChannel(deliveries=deliveries)])
    return NotificationService(
        manager=NotificationManager(default_channel="dashboard"),
        channel_registry=registry,
    )


def test_process_and_persist_is_flush_only_and_idempotent(db):
    user, device, alert_row = _seed_owner(db)
    db.commit()
    alert = _domain_alert(user.id, device.id)
    alert.id = alert_row.id  # persist against the real alert row
    deliveries = []
    service = _service_with_dashboard(deliveries)

    result, row = service.process_and_persist(alert, db)
    assert result.completed is True
    assert result.succeeded is True
    assert row is not None and row.status == "sent"
    assert row.is_read is False
    assert row.user_id == user.id
    db.rollback()  # proves flush-only: nothing was committed inside
    assert NotificationRepository().find_duplicate(
        db, alert.id, "dashboard", str(user.id)) is None

    result, row = service.process_and_persist(alert, db)
    db.commit()
    # The rollback above erased the first row, so this resend is correct.
    assert len(deliveries) == 2
    again, existing = service.process_and_persist(alert, db)
    assert "duplicate" in (again.error or "")
    assert existing is not None and existing.id == row.id
    assert len(deliveries) == 2  # no resend on duplicate


def test_process_and_persist_failure_still_persists_without_raising(db):
    from app.notifications.application import NotificationChannelSender

    class _Boom(NotificationChannelSender):
        channel = NotificationChannel.DASHBOARD

        def _deliver(self, request):
            raise RuntimeError("transport down")

    user, device, alert_row = _seed_owner(db)
    db.commit()
    alert = _domain_alert(user.id, device.id)
    alert.id = alert_row.id
    service = NotificationService(
        manager=NotificationManager(default_channel="dashboard"),
        channel_registry=NotificationChannelRegistry(channels=[_Boom()]),
    )
    result, row = service.process_and_persist(alert, db)  # must not raise
    assert result.completed is True
    assert result.succeeded is False
    assert row is not None and row.status == "failed"


def test_process_and_persist_rejects_non_uuid_owner(db):
    user, device, alert_row = _seed_owner(db)
    db.commit()
    alert = _domain_alert(user.id, device.id)
    alert.id = alert_row.id
    service = _service_with_dashboard([])
    result, row = service.process_and_persist(alert, db, user_id="not-a-uuid")
    assert row is None
    assert result.send_result is None
    assert "UUID" in (result.error or "")


def test_simulated_result_is_completed_but_not_succeeded(clean_env):
    service = NotificationService(
        manager=NotificationManager(default_channel="sms"),
        channel_registry=NotificationChannelRegistry(
            channels=[LoggingSmsChannel(SmsConfig(simulated=True))]),
    )
    result = service.process(_domain_alert(uuid4()))
    assert result.completed is True
    assert result.succeeded is False
    assert result.send_result is not None
    assert result.send_result.status is NotificationStatus.SIMULATED
