"""History API tests: real router and persistence, no production startup."""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.acquisition.normalizer import NormalizedReading
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.classification.domain import TrafficClassification
from app.database.application.persistence_service import PersistenceService
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import (
    AlertORM,
    DeviceORM,
    DeviceSensorORM,
    SensorReadingORM,
    UserORM,
)
from app.database.infrastructure.session import get_db
from app.events.domain import Alert
from app.history.api.router import router
from app.qos.domain import QoSMetric


def _seed(session_factory):
    with session_factory() as db:
        d1 = DeviceORM(code="CAVA-001", name="Cava", location="Lab",
                       device_type="cold_room", status="active")
        d2 = DeviceORM(code="CAVA-002", name="Cava2", location="Lab",
                       device_type="cold_room", status="active")
        user = UserORM(
            id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            name="system", email="system@coldchain.local",
            password_hash="!", role="system",
        )
        db.add_all([d1, d2, user])
        db.flush()
        device_id, user_id = d1.id, user.id
        db.add_all([
            DeviceSensorORM(device_id=device_id, sensor_type=sensor)
            for sensor in ("temperature", "humidity", "energy")
        ])
        db.commit()

    persistence = PersistenceService()
    for i in range(3):
        timestamp = f"2026-09-02T0{i}:00:00+00:00"
        readings = [
            NormalizedReading("CAVA-001", "cold_room", "temperature",
                              5.0 + i, timestamp, 5.0),
            NormalizedReading("CAVA-001", "cold_room", "humidity",
                              80.0, timestamp, 80.0),
            NormalizedReading("CAVA-001", "cold_room", "energy",
                              1.0, timestamp, "on"),
        ]
        now = datetime.now(timezone.utc)
        classification = TrafficClassification(
            id=uuid.uuid4(), reading_id=uuid.uuid4(), criticality=5.0,
            priority="HIGH", queue="WFQ", classification_time=now, timestamp=now,
        )
        qos = QoSMetric(
            id=uuid.uuid4(), classification_id=classification.id,
            latency=0.1, packet_loss=0.0, throughput=100.0,
            pdr=100.0, jitter=0.01, timestamp=now,
        )
        alert = Alert(
            id=uuid.uuid4(), device_id=device_id, user_id=user_id,
            type="TEMPERATURE_EXCEEDED", message="test", criticality=5.0,
            acknowledged=False, created_at=now,
        )
        with session_factory() as db:
            persistence.persist_bundle(
                db, readings=readings, device_id=device_id,
                classification=classification, qos_metric=qos, alerts=[alert],
            )


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    try:
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, future=True)
        _seed(factory)
        yield factory
    finally:
        engine.dispose()


@pytest.fixture()
def client(session_factory, monkeypatch):
    def forbid_external_startup(*args, **kwargs):
        pytest.fail("History API tests must not start MQTT/workers or use production DB sessions")

    # Fail fast if a future fixture accidentally reintroduces production startup.
    monkeypatch.setattr("paho.mqtt.client.Client", forbid_external_startup)
    monkeypatch.setattr(
        "app.acquisition.pipeline.AcquisitionPipeline.start", forbid_external_startup,
    )
    monkeypatch.setattr(
        "app.database.infrastructure.session.SessionLocal", forbid_external_startup,
    )

    app = FastAPI()
    app.include_router(router)

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=uuid.uuid4(), email="auditor@example.com", name="Auditor",
        role="auditor", is_active=True,
    )
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_pagination(client):
    r = client.get("/history/readings?page=1&per_page=2")
    assert r.status_code == 200
    assert r.json()["total"] == 3
    assert r.json()["count"] == 2
    r = client.get("/history/readings?page=2&per_page=2")
    assert r.json()["count"] == 1


def test_dashboard_summary_counts_all_devices_and_only_unacknowledged_alerts(
    client, session_factory
):
    with session_factory() as db:
        device = db.query(DeviceORM).filter_by(code="CAVA-001").one()
        user = db.query(UserORM).one()
        db.add_all([
            DeviceORM(code=f"EXTRA-{i}", name="Extra", location="Lab",
                      device_type="cold_room", status="error" if i < 7 else "active")
            for i in range(105)
        ])
        # Critical alerts older than the five newest rows must still count.
        db.add_all([
            AlertORM(device_id=device.id, user_id=user.id,
                     type="TEMPERATURE_EXCEEDED", message="old critical",
                     criticality=7.0, acknowledged=False,
                     created_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
            for _ in range(8)
        ])
        db.add(AlertORM(device_id=device.id, user_id=user.id,
                        type="TEMPERATURE_EXCEEDED", message="acknowledged",
                        criticality=9.0, acknowledged=True))
        db.commit()

    summary = client.get("/history/summary").json()
    assert summary["total_devices"] == 107
    assert summary["active_devices"] == 100
    assert summary["error_devices"] == 7
    assert summary["total_alerts"] == 12
    assert summary["active_alerts"] == 11
    assert summary["critical_active_alerts"] == 8
    recent = client.get("/history/alerts?per_page=5").json()["results"]
    assert len(recent) == 5  # Independent of the global indicators.
    assert sum(a["criticality"] >= 7 and not a["acknowledged"] for a in recent) < 8


def test_summary_distinguishes_uncalculated_criticality(client, session_factory):
    with session_factory() as db:
        device = db.query(DeviceORM).first()
        user = db.query(UserORM).first()
        db.add_all([
            AlertORM(device_id=device.id, user_id=user.id,
                     type="TEMPERATURE_EXCEEDED", message="sin qos",
                     criticality=None, acknowledged=False),
            AlertORM(device_id=device.id, user_id=user.id,
                     type="TEMPERATURE_EXCEEDED", message="con qos",
                     criticality=9.0, acknowledged=False),
        ])
        db.commit()

    summary = client.get("/history/summary").json()
    assert summary["alerts_without_criticality"] == 1
    assert summary["active_alerts"] == 5
    # NULL is not counted as a critical measurement; only the real 9.0 is.
    assert summary["critical_active_alerts"] == 1


def test_alert_pages_preserve_null_scores_and_timestamp_ties(client, session_factory):
    with session_factory() as db:
        device = db.query(DeviceORM).first()
        user = db.query(UserORM).first()
        db.add_all([
            AlertORM(
                device_id=device.id, user_id=user.id,
                type="ENERGY_STATE_ANOMALY", message="Energy state (off)",
                criticality=None, acknowledged=False,
                created_at=datetime(2026, 11, 21, tzinfo=timezone.utc),
            )
            for _ in range(65)
        ])
        db.commit()

    pages = [
        client.get(
            "/history/alerts",
            params={"type": "ENERGY_STATE_ANOMALY", "page": page, "per_page": 20},
        ).json()
        for page in range(1, 5)
    ]
    assert all(page["total"] == 65 for page in pages)
    assert [len(page["results"]) for page in pages] == [20, 20, 20, 5]
    rows = [row for page in pages for row in page["results"]]
    assert len({row["id"] for row in rows}) == 65
    assert all(row["criticality"] is None for row in rows)
    assert [row["id"] for row in rows] == sorted(
        (row["id"] for row in rows), reverse=True
    )
    summary = client.get("/history/summary").json()
    assert summary["alerts_without_criticality"] == 65
    assert summary["active_alerts"] == 68


def test_filter_device(client):
    r = client.get("/history/readings?device_code=CAVA-001&page=1&per_page=10")
    assert r.json()["total"] == 3
    r = client.get("/history/readings?device_code=NOEXISTE&page=1&per_page=10")
    assert r.json()["total"] == 0
    assert r.json()["results"] == []


def test_404(client):
    r = client.get(f"/history/readings/{uuid.uuid4()}")
    assert r.status_code == 404
    r = client.get(f"/history/alerts/{uuid.uuid4()}")
    assert r.status_code == 404


def test_400_per_page(client):
    r = client.get("/history/readings?page=1&per_page=200")
    assert r.status_code in (400, 422)


def test_bundle(client, session_factory):
    with session_factory() as db:
        reading_id = db.query(SensorReadingORM).first().id
    r = client.get(f"/history/readings/{reading_id}/bundle")
    assert r.status_code == 200
    assert r.json()["sensor_reading"]["id"] == str(reading_id)
    assert r.json()["alerts_legacy"] is True


def test_v2_bundle_links_only_its_own_alert_and_latest_values_skip_null_siblings(
    client, session_factory
):
    with session_factory() as db:
        device = db.query(DeviceORM).filter_by(code="CAVA-001").one()
        user = db.query(UserORM).one()
        temperature = SensorReadingORM(
            device_id=device.id, temperature=9.5, humidity=None, energy=None,
            timestamp=datetime(2026, 9, 2, 5, tzinfo=timezone.utc),
            source_message_id=uuid.uuid4(), sensor_name="temperature",
            processing_version=2,
        )
        humidity = SensorReadingORM(
            device_id=device.id, temperature=None, humidity=82.0, energy=None,
            timestamp=datetime(2026, 9, 2, 6, tzinfo=timezone.utc),
            source_message_id=uuid.uuid4(), sensor_name="humidity",
            processing_version=2,
        )
        db.add_all([temperature, humidity])
        db.flush()
        db.add_all([
            AlertORM(
                device_id=device.id, user_id=user.id, type="TEMPERATURE_EXCEEDED",
                message="temperature", criticality=5.0, reading_id=temperature.id,
            ),
            AlertORM(
                device_id=device.id, user_id=user.id, type="HUMIDITY_ABOVE_MAX",
                message="humidity", criticality=5.0, reading_id=humidity.id,
            ),
        ])
        db.commit()
        temperature_id, humidity_id = temperature.id, humidity.id

    bundle = client.get(f"/history/readings/{temperature_id}/bundle")
    assert bundle.status_code == 200
    assert bundle.json()["alerts_legacy"] is False
    assert [alert["reading_id"] for alert in bundle.json()["alerts"]] == [str(temperature_id)]

    latest = client.get("/history/devices/CAVA-001/latest-values")
    assert latest.status_code == 200
    assert latest.json()["temperature"]["id"] == str(temperature_id)
    assert latest.json()["humidity"]["id"] == str(humidity_id)
    # The latest v2 humidity row has no energy; retain the latest non-NULL
    # energy value instead of treating its NULL as a disabled sensor/value.
    assert latest.json()["energy"]["energy"] == "on"


def test_readings_filter_processing_version(client):
    assert client.get("/history/readings?processing_version=1").json()["total"] == 3
    assert client.get("/history/readings?processing_version=2").json()["total"] == 0
    assert client.get("/history/readings?processing_version=3").status_code == 400


def test_trends(client):
    r = client.get("/history/readings/trends?interval=hour")
    assert r.status_code == 200


def test_qos_trends_preserve_null_aggregates(client, session_factory):
    from app.database.infrastructure.models import QoSMetricORM

    with session_factory() as db:
        for metric in db.query(QoSMetricORM):
            metric.latency = None
            metric.packet_loss = None
            metric.pdr = None
            metric.jitter = None
            metric.throughput = None
        db.commit()
    rows = client.get("/history/qos/trends?interval=hour&processing_version=1").json()
    assert rows
    for row in rows:
        assert row["avg_latency"] is None
        assert row["avg_packet_loss"] is None
        assert row["avg_pdr"] is None
        assert row["avg_throughput"] is None
        assert row["avg_jitter"] is None
    r = client.get("/history/qos/trends?interval=hour")
    assert r.status_code == 200


def test_summary(client):
    r = client.get("/history/summary")
    assert r.status_code == 200
    assert r.json()["total_readings"] == 3
    # Agregado de energía: 3 lecturas con energy='on', sin nulos.
    assert r.json()["energy_by_state"] == {"on": 3}


def test_predictions_empty(client):
    r = client.get("/history/predictions?page=1&per_page=5")
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_requires_authentication(client):
    client.app.dependency_overrides.pop(get_current_user)
    r = client.get("/history/readings")
    assert r.status_code == 401
