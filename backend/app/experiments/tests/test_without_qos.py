"""TSK-059.7 — WITHOUT_QOS branch, run holder, metrics, run control API."""

import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.acquisition.message_queue import MessageQueue
from app.acquisition.normalizer import NormalizedReading
from app.acquisition.pipeline import _worker_loop
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.database.application.persistence_service import PersistenceService
from app.database.infrastructure import session as session_module
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import (
    AlertORM,
    DeviceORM,
    ExperimentMetricORM,
    QoSMetricORM,
    SensorReadingORM,
    TrafficClassificationORM,
    UserORM,
)
from app.database.infrastructure.repositories import (
    DeviceRepository,
    DeviceSensorRepository,
    ExperimentMetricRepository,
    ExperimentRunRepository,
)
from app.database.infrastructure.session import get_db
from app.events.application.event_processing_service import (
    EventProcessingService,
    criticality_for_breaches,
)
from app.events.domain import ThresholdConfig
from app.experiments import active
from app.experiments.api import router
from app.qos.application.qos_metrics_service import QoSMetricsService
from app.qos.application.traffic_planning_service import TrafficPlanningService

SYSTEM_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")
THRESHOLDS = dict(
    min_temperature=0.0,
    max_temperature=4.0,
    min_humidity=85.0,
    max_humidity=90.0,
    allowed_energy_states=frozenset({"on"}),
)


@pytest.fixture()
def db_factory():
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
    factory = sessionmaker(bind=engine, future=True)
    yield factory
    engine.dispose()


@pytest.fixture(autouse=True)
def _no_active_run():
    active.clear_active_run()
    yield
    active.clear_active_run()


def _seed_device(db, code="CAVA-EXP"):
    d = DeviceRepository().create(
        db, code=code, name="Cava", location="Lab",
        device_type="cold_room", status="active",
    )
    db.commit()
    for sensor_type in ("temperature", "humidity", "energy"):
        DeviceSensorRepository().create(db, device_id=d.id, sensor_type=sensor_type)
    db.add(
        UserORM(
            id=SYSTEM_ID, name="system", email="system@coldchain.local",
            password_hash="!", role="system", is_active=True,
        )
    )
    db.commit()
    return d


def _message(code="CAVA-EXP", temperature=9.5, humidity=87.0, energy="on"):
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    return {
        "topic": f"coldchain/device/{code}/telemetry",
        "payload": {
            "device_code": code,
            "device_type": "cold_room",
            "temperature": temperature,
            "humidity": humidity,
            "energy": energy,
            "timestamp": now,
        },
        "device_origin": {"device_code": code, "device_type": "cold_room"},
        "received_at": now,
    }


def _run_worker(db_factory, messages, seconds=3.0, code="CAVA-EXP"):
    """Drive _worker_loop with sqlite-backed sessions; return app_state."""
    with db_factory() as db:
        device = db.query(DeviceORM).filter_by(code=code).first()
        device_id = device.id
    state = SimpleNamespace(
        classifications=[],
        events=[],
        alerts=[],
        enriched_events=[],
        notifications=[],
        qos_service=TrafficPlanningService(),
        qos_metrics_service=QoSMetricsService(),
        qos_records=[],
        event_processing_service=EventProcessingService(
            ThresholdConfig(**THRESHOLDS),
            device_mapping={code: device_id},
            user_id=SYSTEM_ID,
        ),
        persistence_service=PersistenceService(),
    )
    queue = MessageQueue(100)
    for m in messages:
        queue.append(m)
    stop = threading.Event()
    timer = threading.Timer(seconds, stop.set)
    timer.start()
    try:
        with mock.patch.object(session_module, "SessionLocal", db_factory):
            _worker_loop(queue, state, stop)
    finally:
        timer.cancel()
    return state


# --- holder ------------------------------------------------------------------

def test_resolve_defaults_to_with_qos_without_run():
    assert active.get_active_run() is None
    run_id, scenario = active.resolve_scenario()
    assert run_id is None and scenario == "WITH_QOS"


def test_set_get_clear_and_double_set_guarded():
    rid = uuid.uuid4()
    active.set_active_run(rid, "WITHOUT_QOS")
    assert active.get_active_run() == (rid, "WITHOUT_QOS")
    with pytest.raises(RuntimeError):
        active.set_active_run(uuid.uuid4(), "WITH_QOS")
    active.clear_active_run()
    assert active.get_active_run() is None
    active.clear_active_run()  # idempotent
    with pytest.raises(ValueError):
        active.set_active_run(uuid.uuid4(), "WITH_CACHE")
    with pytest.raises(TypeError):
        active.set_active_run("not-a-uuid", "WITH_QOS")


# --- rule-derived criticality --------------------------------------------------

def test_criticality_for_breaches():
    class _E:
        def __init__(self, breached):
            self.breached = breached

    assert criticality_for_breaches([_E(True)]) == 5.0
    assert criticality_for_breaches([_E(True), _E(True)]) == 7.0
    assert criticality_for_breaches([_E(True)] * 5) == 9.0
    assert criticality_for_breaches([]) == 3.0


def test_process_without_classification_uses_rule_criticality():
    svc = EventProcessingService(
        ThresholdConfig(**THRESHOLDS),
        device_mapping={"CAVA-EXP": uuid.uuid4()},
        user_id=SYSTEM_ID,
    )
    reading = NormalizedReading(
        device_code="CAVA-EXP", device_type="cold_room", sensor_name="temperature",
        value=9.5, timestamp=datetime.now(timezone.utc).isoformat(), raw_value=9.5,
    )
    result = svc.process([reading], None)
    assert result["classification_id"] is None
    assert result["alert_count"] == 1
    assert result["alerts"][0].criticality == 5.0


# --- persist_bundle without classification --------------------------------------

def test_persist_bundle_without_classification(db_factory):
    with db_factory() as db:
        d = _seed_device(db)
        run = ExperimentRunRepository().create(db, scenario="WITHOUT_QOS")
        db.commit()
        run_id, reading_device_id = run.id, d.id
    from app.events.domain import Alert as DomainAlert

    with db_factory() as db:
        alert = DomainAlert(
            id=uuid.uuid4(), device_id=reading_device_id, user_id=SYSTEM_ID,
            type="TEMPERATURE_EXCEEDED", message="warm", criticality=5.0,
            acknowledged=False, created_at=datetime.now(timezone.utc),
        )
        readings = [
            NormalizedReading(device_code="CAVA-EXP", device_type="cold_room", sensor_name="temperature", value=9.5, timestamp="2026-10-05T12:00:00+00:00", raw_value=9.5),
            NormalizedReading(device_code="CAVA-EXP", device_type="cold_room", sensor_name="humidity", value=87.0, timestamp="2026-10-05T12:00:00+00:00", raw_value=87.0),
            NormalizedReading(device_code="CAVA-EXP", device_type="cold_room", sensor_name="energy", value=1.0, timestamp="2026-10-05T12:00:00+00:00", raw_value="on"),
        ]
        out = PersistenceService().persist_bundle(
            db, readings=readings, device_id=reading_device_id,
            classification=None, alerts=[alert], run_id=run_id,
        )
        assert out["traffic_classification"] is None
        assert out["qos_metric"] is None
        assert out["sensor_reading"].run_id == run_id
        assert out["alerts"][0].run_id == run_id
    with db_factory() as db:
        assert db.query(TrafficClassificationORM).count() == 0
        assert db.query(QoSMetricORM).count() == 0
        assert db.query(SensorReadingORM).count() == 1
        assert db.query(AlertORM).count() == 1


# --- full branch WITHOUT_QOS ------------------------------------------------------

def test_without_qos_branch_end_to_end(db_factory):
    with db_factory() as db:
        d = _seed_device(db)
        run = ExperimentRunRepository().create(db, scenario="WITHOUT_QOS")
        db.commit()
        run_id = run.id
    active.set_active_run(run_id, "WITHOUT_QOS")
    state = _run_worker(db_factory, [_message()])
    assert len(state.alerts) == 1  # runtime path also produced the alert
    with db_factory() as db:
        assert db.query(TrafficClassificationORM).count() == 0
        assert db.query(QoSMetricORM).count() == 0
        readings = db.query(SensorReadingORM).all()
        assert len(readings) == 1
        assert readings[0].run_id == run_id
        alerts = db.query(AlertORM).all()
        assert len(alerts) == 1
        assert alerts[0].run_id == run_id
        assert alerts[0].criticality == 5.0  # rule-derived, not QoS
        metrics = {m.metric_type: m for m in db.query(ExperimentMetricORM).filter_by(run_id=run_id).all()}
    assert state.classifications == []  # nothing classified
    assert state.qos_records == []  # scheduler never ran
    for key in ("messages_received", "backlog", "readings_persisted", "alerts_generated",
                "ingest_to_persist_ms", "ingest_to_alert_ms"):
        assert key in metrics, key
        assert metrics[key].value >= 0
    assert "messages_invalid" not in metrics


def test_with_qos_branch_unchanged(db_factory):
    with db_factory() as db:
        d = _seed_device(db)
        run = ExperimentRunRepository().create(db, scenario="WITH_QOS")
        db.commit()
        run_id = run.id
    active.set_active_run(run_id, "WITH_QOS")
    state = _run_worker(db_factory, [_message()])
    with db_factory() as db:
        assert db.query(TrafficClassificationORM).count() == 1
        assert db.query(QoSMetricORM).count() == 1
        readings = db.query(SensorReadingORM).all()
        assert len(readings) == 1 and readings[0].run_id == run_id
        alerts = db.query(AlertORM).all()
        assert len(alerts) == 1 and alerts[0].run_id == run_id
        tc = db.query(TrafficClassificationORM).first()
        assert alerts[0].criticality == tc.criticality == 9.0
    assert len(state.classifications) == 3  # one per reading
    assert len(state.qos_records) == 3  # planning executed


def test_no_run_legacy_behavior(db_factory):
    with db_factory() as db:
        _seed_device(db)
    state = _run_worker(db_factory, [_message()])
    with db_factory() as db:
        assert db.query(TrafficClassificationORM).count() == 1
        assert db.query(QoSMetricORM).count() == 1
        assert db.query(SensorReadingORM).first().run_id is None
        assert db.query(AlertORM).first().run_id is None
        assert db.query(ExperimentMetricORM).count() == 0
    assert len(state.classifications) == 3


def test_invalid_message_records_metric_without_persisting(db_factory):
    with db_factory() as db:
        _seed_device(db)
        run = ExperimentRunRepository().create(db, scenario="WITHOUT_QOS")
        db.commit()
        run_id = run.id
    active.set_active_run(run_id, "WITHOUT_QOS")
    bad = {
        "topic": "coldchain/device/CAVA-EXP/telemetry",
        "payload": {"device_code": "CAVA-EXP", "device_type": "cold_room",
                    "timestamp": datetime.now(timezone.utc).isoformat()},
        "device_origin": {"device_code": "CAVA-EXP", "device_type": "cold_room"},
        "received_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
    }
    _run_worker(db_factory, [bad])
    with db_factory() as db:
        assert db.query(SensorReadingORM).count() == 0
        types = [m.metric_type for m in db.query(ExperimentMetricORM).filter_by(run_id=run_id).all()]
        assert "messages_invalid" in types
        assert "readings_persisted" not in types


# --- run control API --------------------------------------------------------------

def _api_client(Session, role="admin"):
    app = FastAPI()
    from app.experiments.api import router as exp_router

    app.include_router(exp_router)

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=uuid.uuid4(), email=f"{role}@x.com", name=role, role=role, is_active=True,
    )
    return TestClient(app)


def test_run_start_finish_lifecycle(db_factory):
    c = _api_client(db_factory)
    try:
        r = c.post("/experiment-runs", json={"scenario": "WITHOUT_QOS"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["scenario"] == "WITHOUT_QOS"
        assert body["finished_at"] is None
        assert "min_temperature" in (body["config_snapshot"] or "")
        assert active.get_active_run()[0] == uuid.UUID(body["id"])
        # second start conflicts while active
        r2 = c.post("/experiment-runs", json={"scenario": "WITH_QOS"})
        assert r2.status_code == 409, r2.text
        # finish releases
        f = c.post(f"/experiment-runs/{body['id']}/finish")
        assert f.status_code == 200, f.text
        assert f.json()["finished_at"] is not None
        assert active.get_active_run() is None
    finally:
        active.clear_active_run()


def test_run_start_validation_and_roles(db_factory):
    c = _api_client(db_factory)
    try:
        r = c.post("/experiment-runs", json={"scenario": "WITH_CACHE"})
        assert r.status_code == 400, r.text
        c_admin = c
        c_op = _api_client(db_factory, role="operador")
        r = c_op.post("/experiment-runs", json={"scenario": "WITH_QOS"})
        assert r.status_code == 403, r.text
        assert active.get_active_run() is None
        r = c_admin.post(f"/experiment-runs/{uuid.uuid4()}/finish")
        assert r.status_code == 404, r.text
    finally:
        active.clear_active_run()
