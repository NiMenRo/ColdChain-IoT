"""run_id scoping for history endpoints (no migration).

TC/QoS rows carry no run_id (UML 1:1 via SensorReading); the run linkage
resolves through SensorReading.run_id (Alert.run_id directly). Two runs
with distinct priority distributions must filter independently, and legacy
NULL rows must appear only in unfiltered (global) mode.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.infrastructure.base import Base
from app.database.infrastructure.models import (
    AlertORM,
    DeviceORM,
    DeviceSensorORM,
    ExperimentRunORM,
    QoSMetricORM,
    SensorReadingORM,
    TrafficClassificationORM,
    UserORM,
)
from app.history.api.router import _parse_run_id
from app.history.application.history_service import HistoryService


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


def _seed_run(db, scenario, priorities):
    """One device + one run; one reading+TC(+QoS) per priority; one alert."""
    now = datetime.now(timezone.utc)
    user = UserORM(name="u", email=f"{uuid.uuid4().hex}@e.com",
                   password_hash="h", role="operador")
    db.add(user)
    db.flush()
    dev = DeviceORM(code=f"D-{uuid.uuid4().hex[:6]}", name="d", location="l",
                    device_type="cold_room", status="active")
    db.add(dev)
    db.flush()
    run = ExperimentRunORM(scenario=scenario, started_at=now)
    db.add(run)
    db.flush()
    queue = {"high": "WFQ", "medium": "Round Robin", "low": "FIFO"}
    crit = {"high": 8.0, "medium": 6.0, "low": 3.0}
    for prio in priorities:
        reading = SensorReadingORM(device_id=dev.id, temperature=1.0,
                                   humidity=87.0, energy="on",
                                   timestamp=now, run_id=run.id)
        db.add(reading)
        db.flush()
        tc = TrafficClassificationORM(
            reading_id=reading.id, criticality=crit[prio], priority=prio,
            queue=queue[prio], classification_time=now, timestamp=now)
        db.add(tc)
        db.flush()
        db.add(QoSMetricORM(classification_id=tc.id, latency=0.5,
                            packet_loss=0.0, throughput=100.0, pdr=100.0,
                            jitter=0.01, timestamp=now))
    db.add(AlertORM(device_id=dev.id, user_id=user.id,
                    type="TEMPERATURE_EXCEEDED", message="m", criticality=5.0,
                    acknowledged=False, created_at=now, run_id=run.id))
    db.flush()
    return run.id


def _seed_legacy(db):
    now = datetime.now(timezone.utc)
    user = UserORM(name="u", email=f"{uuid.uuid4().hex}@e.com",
                   password_hash="h", role="operador")
    db.add(user)
    db.flush()
    dev = DeviceORM(code=f"D-{uuid.uuid4().hex[:6]}", name="d", location="l",
                    device_type="cold_room", status="active")
    db.add(dev)
    db.flush()
    reading = SensorReadingORM(device_id=dev.id, temperature=1.0,
                               humidity=87.0, energy="on",
                               timestamp=now, run_id=None)
    db.add(reading)
    db.flush()
    db.add(TrafficClassificationORM(
        reading_id=reading.id, criticality=3.0, priority="low",
        queue="FIFO", classification_time=now, timestamp=now))
    db.flush()


def test_parse_run_id_validation():
    assert _parse_run_id(None) is None
    assert _parse_run_id("") is None
    rid = uuid.uuid4()
    assert _parse_run_id(str(rid)) == rid
    with pytest.raises(HTTPException) as exc:
        _parse_run_id("not-a-uuid")
    assert exc.value.status_code == 400


def test_run_filter_isolates_distinct_distributions(db):
    run_a = _seed_run(db, "WITH_QOS", ["high", "high", "medium"])
    run_b = _seed_run(db, "WITHOUT_QOS", ["low"])
    _seed_legacy(db)
    db.commit()
    svc = HistoryService()

    glob = svc.summary(db)
    assert glob["run_id"] is None
    assert glob["traffic_by_priority"] == {"high": 2, "medium": 1, "low": 2}
    assert glob["total_readings"] == 5
    # Plain row counts (never bare-column aggregates: Postgres rejects them).
    assert glob["total_qos_metrics"] == 4
    assert glob["total_classifications"] == 5  # 4 run + 1 legacy

    a = svc.summary(db, run_id=run_a)
    assert a["run_id"] == str(run_a)
    assert a["traffic_by_priority"] == {"high": 2, "medium": 1}
    assert a["total_readings"] == 3
    assert a["total_alerts"] == 1
    assert a["total_qos_metrics"] == 3

    b = svc.summary(db, run_id=run_b)
    assert b["traffic_by_priority"] == {"low": 1}
    assert b["total_readings"] == 1
    # Legacy NULL rows excluded from scoped mode.
    assert a["total_readings"] + b["total_readings"] == glob["total_readings"] - 1

    unknown = uuid.uuid4()
    empty = svc.summary(db, run_id=unknown)
    assert empty["traffic_by_priority"] == {}
    assert empty["total_readings"] == 0


def test_list_endpoints_accept_run_id(db):
    run_a = _seed_run(db, "WITH_QOS", ["high", "medium"])
    run_b = _seed_run(db, "WITHOUT_QOS", ["low"])
    _seed_legacy(db)
    db.commit()
    svc = HistoryService()

    total, items = svc.classifications.list(db, run_id=run_a)
    assert total == 2
    assert {i.priority for i in items} == {"high", "medium"}
    total, _ = svc.classifications.list(db, run_id=run_b)
    assert total == 1

    total, items = svc.qos.list(db, run_id=run_a)
    assert total == 2
    total, _ = svc.qos.list(db, run_id=run_b)
    assert total == 1

    total, _ = svc.alerts.list(db, run_id=run_a)
    assert total == 1
    total, _ = svc.alerts.list(db, run_id=run_b)
    assert total == 1

    total, _ = svc.readings.list(db, run_id=run_a)
    assert total == 2

    rows = svc.qos.trends(db, run_id=run_a)
    assert len(rows) >= 1
    rows = svc.readings.trends(db, run_id=run_b)
    assert len(rows) >= 1


def test_summary_rejects_non_uuid_run_id(db):
    with pytest.raises(ValueError, match="run_id must be a UUID"):
        HistoryService().summary(db, run_id="nope")
