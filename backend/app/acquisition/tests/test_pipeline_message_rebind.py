"""Regression: worker loop must not rebind `message` while dispatching.

On 2026-10-10 ~2900 WITH_QOS bundles were silently dropped: after the first
alert of a message was dispatched, `message` was rebound to the notification
text, so the next reading's `message.get(...)` raised AttributeError and the
outer handler skipped bundle persistence (readings + TC + alerts), while the
in-memory lists kept the partial results. Messages without alerts were
unaffected, which is why WITHOUT_QOS and all-normal WITH_QOS bundles kept
persisting and every surviving TC was C=3.0/low.

This test drives the real `_worker_loop` with one breach-first message and
asserts all three readings classify AND every durable row exists.
"""

from __future__ import annotations

import os
import smtplib
import tempfile
import threading
import time
import types
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.acquisition.pipeline import _critical_email_message, _worker_loop
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import (
    AlertORM,
    DeviceORM,
    DeviceSensorORM,
    NotificationORM,
    SensorReadingORM,
    TrafficClassificationORM,
    UserORM,
)
from app.database.application.persistence_service import PersistenceService
from app.events.application.event_processing_service import EventProcessingService
from app.events.domain import ThresholdConfig
from app.history.infrastructure.alert_history_repository import AlertHistoryRepository
from app.notifications.application import (
    NotificationChannelRegistry,
    NotificationService,
    production_channels,
)
from app.auth.sessions import active_sessions
from app.qos.application.qos_metrics_service import QoSMetricsService
from app.qos.application.traffic_planning_service import TrafficPlanningService


class _ScriptedQueue:
    """One message, then idle (plus backlog introspection)."""

    def __init__(self, message):
        self._message = message
        self._served = False

    def pop(self):
        if not self._served:
            self._served = True
            return self._message
        return None

    def get_all(self):
        return []


def test_critical_email_formats_alert_time_in_colombia():
    alert = types.SimpleNamespace(
        type="TEMPERATURE_EXCEEDED",
        message="Temperatura fuera de rango (9.5 °C) (0-4 °C)",
        criticality=8,
        created_at=datetime(2026, 10, 27, 18, 0, tzinfo=timezone.utc),
    )

    email = _critical_email_message(alert, "CAVA-001")

    assert "Fecha y hora: 27/10/2026 – 13:00 (hora Colombia)" in email


def test_breach_first_message_persists_whole_bundle(monkeypatch, tmp_path):
    db_file = str(tmp_path / "worker_repro.db")
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False)

    with TestSession() as db:
        with db.begin():
            dev = DeviceORM(code="CAVA-001", name="Cava", location="Lab",
                            device_type="cold_room", status="active")
            db.add(dev)
            db.flush()
            for sensor in ("temperature", "humidity", "energy"):
                db.add(DeviceSensorORM(device_id=dev.id, sensor_type=sensor))
            from app.database.infrastructure.models import UserORM
            owner = UserORM(name="sys", email="sys@example.com",
                            password_hash="h", role="system")
            db.add(owner)
            db.flush()
            dev_id, user_id = dev.id, owner.id

    # The worker resolves SessionLocal at call time: point it at sqlite.
    import app.database.infrastructure.session as session_module
    monkeypatch.setattr(session_module, "SessionLocal", TestSession)

    thresholds = ThresholdConfig(min_temperature=0.0, max_temperature=4.0,
                                 min_humidity=85.0, max_humidity=90.0,
                                 allowed_energy_states=frozenset({"on"}))
    event_service = EventProcessingService(threshold_config=thresholds)
    event_service.set_device_mapping({"CAVA-001": dev_id})
    event_service.set_user_id(user_id)

    state = types.SimpleNamespace(
        classifications=[],
        events=[],
        alerts=[],
        enriched_events=[],
        notifications=[],
        qos_service=TrafficPlanningService(),
        qos_metrics_service=QoSMetricsService(),
        qos_records=[],
        persistence_service=PersistenceService(),
        event_processing_service=event_service,
        notification_service=NotificationService(),
    )

    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    message = {
        "topic": "coldchain/device/CAVA-001/telemetry",
        "payload": {"temperature": 9.5, "humidity": 87.0, "energy": "on",
                    "device_code": "CAVA-001", "device_type": "cold_room",
                    "timestamp": now},
        "device_origin": {"device_code": "CAVA-001", "device_type": "cold_room"},
        "received_at": now,
    }

    stop = threading.Event()
    worker = threading.Thread(target=_worker_loop,
                              args=(_ScriptedQueue(message), state, stop),
                              daemon=True)
    worker.start()
    try:
        deadline = time.time() + 20.0
        while time.time() < deadline:
            if len(state.classifications) >= 3:
                break
            time.sleep(0.2)
        # Give the bundle + notification transactions a moment to commit.
        time.sleep(1.0)
    finally:
        stop.set()
        worker.join(timeout=10.0)

    # All three readings classified (temp HIGH/WFQ first, then the rest).
    assert len(state.classifications) == 3, (
        f"loop aborted early, only {len(state.classifications)} readings classified")
    assert state.classifications[0]["classification"].priority == "high"
    assert state.classifications[0]["classification"].queue == "WFQ"

    with TestSession() as db:
        assert db.query(SensorReadingORM).count() == 1
        assert db.query(TrafficClassificationORM).count() == 1
        assert db.query(AlertORM).count() >= 1
        assert db.query(NotificationORM).count() >= 1
    engine.dispose()


def _seed_fanout_db(TestSession):
    """Device + sensors + system author + mixed human users."""
    with TestSession() as db:
        with db.begin():
            dev = DeviceORM(code="CAVA-001", name="Cava", location="Lab",
                            device_type="cold_room", status="active")
            db.add(dev)
            db.flush()
            for sensor in ("temperature", "humidity", "energy"):
                db.add(DeviceSensorORM(device_id=dev.id, sensor_type=sensor))
            author = UserORM(name="sys", email="sys@example.com",
                             password_hash="h", role="system")
            db.add(author)
            db.flush()
            ids = {}
            for name, email, role, active in [
                ("Admin", "admin@example.com", "admin", True),
                ("Ope", "ope@example.com", "operador", True),
                ("Audi", "audi@example.com", "auditor", True),
                ("SupOff", "supoff@example.com", "supervisor", False),
            ]:
                u = UserORM(name=name, email=email, password_hash="h",
                            role=role, is_active=active)
                db.add(u)
                db.flush()
                ids[role if active or role != "supervisor" else "supervisor_off"] = u.id
            dev_id, author_id = dev.id, author.id
    return dev_id, author_id, ids


def _pump_one_message(TestSession, dev_id, author_id, message, notification_service=None):
    import app.database.infrastructure.session as session_module
    # NOTE: caller must have monkeypatched session_module.SessionLocal already
    # for the worker thread; this helper only builds state + runs the loop.
    thresholds = ThresholdConfig(min_temperature=0.0, max_temperature=4.0,
                                 min_humidity=85.0, max_humidity=90.0,
                                 allowed_energy_states=frozenset({"on"}))
    event_service = EventProcessingService(threshold_config=thresholds)
    event_service.set_device_mapping({"CAVA-001": dev_id})
    event_service.set_user_id(author_id)
    state = types.SimpleNamespace(
        classifications=[],
        events=[],
        alerts=[],
        enriched_events=[],
        notifications=[],
        qos_service=TrafficPlanningService(),
        qos_metrics_service=QoSMetricsService(),
        qos_records=[],
        persistence_service=PersistenceService(),
        event_processing_service=event_service,
        notification_service=notification_service or NotificationService(),
    )
    stop = threading.Event()
    worker = threading.Thread(target=_worker_loop,
                              args=(_ScriptedQueue(message), state, stop),
                              daemon=True)
    worker.start()
    try:
        deadline = time.time() + 20.0
        while time.time() < deadline:
            if len(state.classifications) >= 3:
                break
            time.sleep(0.2)
        time.sleep(1.0)
    finally:
        stop.set()
        worker.join(timeout=10.0)
    return state


def _breach_message():
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    return {
        "topic": "coldchain/device/CAVA-001/telemetry",
        "payload": {"temperature": 9.5, "humidity": 87.0, "energy": "on",
                    "device_code": "CAVA-001", "device_type": "cold_room",
                    "timestamp": now},
        "device_origin": {"device_code": "CAVA-001", "device_type": "cold_room"},
        "received_at": now,
    }


def test_fanout_distributes_to_active_humans_only(monkeypatch, tmp_path):
    """Fan-out policy: admin/operador/auditor actives get own rows.

    System, inactive and unknown users never own rows. Auditor rows are
    read-only by RBAC (no ack/write), but readable via `authenticated`
    endpoints — receiving rows grants no extra power.
    """
    db_file = str(tmp_path / "worker_fanout.db")
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False)
    dev_id, author_id, ids = _seed_fanout_db(TestSession)

    import app.database.infrastructure.session as session_module
    monkeypatch.setattr(session_module, "SessionLocal", TestSession)
    state = _pump_one_message(TestSession, dev_id, author_id, _breach_message())

    assert len(state.alerts) >= 1
    with TestSession() as db:
        rows = db.query(NotificationORM).all()
        owners = {r.user_id for r in rows}
        assert owners == {ids["admin"], ids["operador"], ids["auditor"]}, owners
        # One row per (alert × recipient): no duplicates, all unread.
        assert len(rows) == len(state.alerts) * 3
        assert all(r.is_read is False for r in rows)
        assert all(r.channel == "dashboard" and r.status == "sent" for r in rows)
        for r in rows:
            assert r.recipient == str(r.user_id)
    engine.dispose()


def test_fanout_falls_back_to_alert_author_without_humans(monkeypatch, tmp_path):
    """Legacy fallback: no human recipients → single author-owned row."""
    db_file = str(tmp_path / "worker_fallback.db")
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False)
    with TestSession() as db:
        with db.begin():
            dev = DeviceORM(code="CAVA-001", name="Cava", location="Lab",
                            device_type="cold_room", status="active")
            db.add(dev)
            db.flush()
            for sensor in ("temperature", "humidity", "energy"):
                db.add(DeviceSensorORM(device_id=dev.id, sensor_type=sensor))
            author = UserORM(name="sys", email="sys@example.com",
                             password_hash="h", role="system")
            db.add(author)
            db.flush()
            dev_id, author_id = dev.id, author.id

    import app.database.infrastructure.session as session_module
    monkeypatch.setattr(session_module, "SessionLocal", TestSession)
    state = _pump_one_message(TestSession, dev_id, author_id, _breach_message())

    assert len(state.alerts) >= 1
    with TestSession() as db:
        rows = db.query(NotificationORM).all()
        assert len(rows) == len(state.alerts)
        assert {r.user_id for r in rows} == {author_id}
    engine.dispose()


def test_critical_alert_sends_email_and_is_available_to_dashboard(monkeypatch, tmp_path):
    db_file = str(tmp_path / "worker_critical_notifications.db")
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False)
    dev_id, author_id, ids = _seed_fanout_db(TestSession)
    import app.database.infrastructure.session as session_module
    monkeypatch.setattr(session_module, "SessionLocal", TestSession)
    recipient_id = ids["admin"]
    active_sessions.login(recipient_id, 3600)
    sent_emails = []

    class _FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def starttls(self):
            pass

        def login(self, username, password):
            pass

        def send_message(self, message):
            sent_emails.append(message)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setenv("SMTP_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "alerts@example.com")
    monkeypatch.setenv("SMTP_USERNAME", "alerts@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "test-password")
    notification_service = NotificationService(
        channel_registry=NotificationChannelRegistry(channels=production_channels())
    )

    try:
        state = _pump_one_message(
            TestSession, dev_id, author_id, _breach_message(), notification_service
        )
    finally:
        active_sessions.logout(recipient_id)

    critical_alert_ids = {
        alert.id for alert in state.alerts if alert.criticality >= 8
    }
    assert critical_alert_ids
    assert len(sent_emails) == len(critical_alert_ids)
    assert all(email["To"] == "admin@example.com" for email in sent_emails)

    with TestSession() as db:
        rows = (
            db.query(NotificationORM)
            .filter(
                NotificationORM.user_id == recipient_id,
                NotificationORM.alert_id.in_(critical_alert_ids),
            )
            .all()
        )
        assert {(row.channel, row.status) for row in rows} == {
            ("dashboard", "sent"),
            ("email", "sent"),
        }
        total, dashboard_alerts = AlertHistoryRepository().list(
            db, page=1, per_page=5
        )
        assert total >= len(critical_alert_ids)
        assert critical_alert_ids.intersection({alert.id for alert in dashboard_alerts})

    engine.dispose()
