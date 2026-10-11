"""TSK-059.6 — ExperimentRun/Metric repositories, relations, constraints, history."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.acquisition.normalizer import NormalizedReading
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import (
    AlertORM,
    DeviceORM,
    SensorReadingORM,
    UserORM,
)
from app.database.infrastructure.repositories import (
    DeviceRepository,
    ExperimentMetricRepository,
    ExperimentRunRepository,
    SensorReadingRepository,
)


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
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


# --- ExperimentRun ----------------------------------------------------------

def test_create_run_with_qos(db):
    run = ExperimentRunRepository().create(db, scenario="WITH_QOS")
    db.commit()
    assert run.scenario == "WITH_QOS"
    assert run.started_at is not None
    assert run.finished_at is None
    assert run.config_snapshot is None


def test_create_run_without_qos_with_snapshot(db):
    run = ExperimentRunRepository().create(
        db,
        scenario="WITHOUT_QOS",
        config_snapshot={"min_temperature": 0.0, "max_temperature": 4.0},
        finished_at=datetime.now(timezone.utc),
    )
    db.commit()
    assert run.scenario == "WITHOUT_QOS"
    assert '"max_temperature": 4.0' in run.config_snapshot
    assert run.finished_at is not None


def test_create_run_invalid_scenario_rejected(db):
    with pytest.raises(ValueError):
        ExperimentRunRepository().create(db, scenario="WITH_CACHE")
    with pytest.raises(ValueError):
        ExperimentRunRepository().create(db, scenario="  ")
    db.rollback()


def test_list_runs_by_scenario_and_get_by_id(db):
    repo = ExperimentRunRepository()
    repo.create(db, scenario="WITH_QOS")
    repo.create(db, scenario="WITHOUT_QOS")
    db.commit()
    total, items = repo.list(db)
    assert total == 2
    total, items = repo.list(db, scenario="WITH_QOS")
    assert total == 1 and items[0].scenario == "WITH_QOS"
    assert repo.get_by_id(db, items[0].id).id == items[0].id
    assert repo.get_by_id(db, uuid.uuid4()) is None
    with pytest.raises(ValueError):
        repo.list(db, scenario="WITH_CACHE")


def test_run_scenario_check_constraint(db):
    import uuid as _uuid
    from sqlalchemy import text

    # Raw SQL bypasses the ORM @validates to exercise the DB CHECK itself.
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO experiment_runs (id, scenario, started_at) "
                "VALUES (:id, 'WITH_CACHE', '2026-10-05T12:00:00+00:00')"
            ),
            {"id": str(_uuid.uuid4())},
        )
        db.flush()
    db.rollback()


# --- ExperimentMetric ---------------------------------------------------------

def test_append_valid_metric(db):
    run = ExperimentRunRepository().create(db, scenario="WITH_QOS")
    db.commit()
    m = ExperimentMetricRepository().append(
        db, run_id=run.id, metric_type="readings_persisted", value=10.0
    )
    db.commit()
    assert m.run_id == run.id
    assert m.metric_type == "readings_persisted"
    assert m.value == 10.0
    assert m.timestamp is not None


def test_all_metric_types_accepted(db):
    run = ExperimentRunRepository().create(db, scenario="WITH_QOS")
    db.commit()
    repo = ExperimentMetricRepository()
    for metric_type in (
        "messages_received",
        "messages_invalid",
        "readings_persisted",
        "alerts_generated",
        "backlog",
        "ingest_to_persist_ms",
        "ingest_to_alert_ms",
    ):
        repo.append(db, run_id=run.id, metric_type=metric_type, value=1.0)
    db.commit()
    total, _ = repo.list(db, run_id=run.id)
    assert total == 7


def test_invalid_metric_type_rejected(db):
    run = ExperimentRunRepository().create(db, scenario="WITH_QOS")
    db.commit()
    with pytest.raises(ValueError):
        ExperimentMetricRepository().append(
            db, run_id=run.id, metric_type="latency", value=1.0
        )
    with pytest.raises(ValueError):
        ExperimentMetricRepository().append(
            db, run_id=run.id, metric_type="pdr", value=1.0
        )
    db.rollback()


def test_metric_type_check_constraint(db):
    import uuid as _uuid
    from sqlalchemy import text

    run = ExperimentRunRepository().create(db, scenario="WITH_QOS")
    db.commit()
    # Raw SQL bypasses the ORM @validates to exercise the DB CHECK itself.
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO experiment_metrics (id, run_id, metric_type, value, timestamp) "
                "VALUES (:id, :run_id, 'throughput', 1.0, '2026-10-05T12:00:00+00:00')"
            ),
            {"id": str(_uuid.uuid4()), "run_id": str(run.id)},
        )
        db.flush()
    db.rollback()


def test_metric_fk_to_missing_run_rejected(db):
    with pytest.raises(IntegrityError):
        ExperimentMetricRepository().append(
            db, run_id=uuid.uuid4(), metric_type="backlog", value=2.0
        )
        db.flush()
    db.rollback()


def test_list_by_run_and_type_deterministic_order(db):
    run = ExperimentRunRepository().create(db, scenario="WITHOUT_QOS")
    db.commit()
    repo = ExperimentMetricRepository()
    repo.bulk(
        db,
        run_id=run.id,
        metrics=[
            {
                "metric_type": "backlog",
                "value": 3.0,
                "timestamp": datetime(2026, 10, 5, 12, 2, tzinfo=timezone.utc),
            },
            {
                "metric_type": "backlog",
                "value": 1.0,
                "timestamp": datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc),
            },
            {
                "metric_type": "backlog",
                "value": 2.0,
                "timestamp": datetime(2026, 10, 5, 12, 1, tzinfo=timezone.utc),
            },
        ],
    )
    db.commit()
    total, items = repo.list(db, run_id=run.id, metric_type="backlog")
    assert total == 3
    assert [i.value for i in items] == [1.0, 2.0, 3.0]
    total, items = repo.list(db, run_id=run.id, metric_type="alerts_generated")
    assert total == 0
    with pytest.raises(ValueError):
        repo.list(db, run_id=run.id, metric_type="latency")


# --- Relations ------------------------------------------------------------------

def _device_with_sensors(db, code="CAVA-EXP"):
    from app.database.infrastructure.repositories import DeviceSensorRepository

    d = DeviceRepository().create(
        db, code=code, name="Cava", location="Lab",
        device_type="cold_room", status="active",
    )
    db.commit()
    for sensor_type in ("temperature", "humidity", "energy"):
        DeviceSensorRepository().create(db, device_id=d.id, sensor_type=sensor_type)
    db.commit()
    return d


def test_run_to_readings_and_alerts(db):
    d = _device_with_sensors(db)
    run = ExperimentRunRepository().create(db, scenario="WITH_QOS")
    db.commit()
    reading = SensorReadingRepository().save(
        db,
        [
            NormalizedReading(device_code=d.code, device_type="cold_room", sensor_name="temperature", value=4.0, timestamp="2026-10-05T12:00:00+00:00", raw_value=4.0),
            NormalizedReading(device_code=d.code, device_type="cold_room", sensor_name="humidity", value=80.0, timestamp="2026-10-05T12:00:00+00:00", raw_value=80.0),
            NormalizedReading(device_code=d.code, device_type="cold_room", sensor_name="energy", value=1.0, timestamp="2026-10-05T12:00:00+00:00", raw_value="on"),
        ],
        d.id,
    )
    reading.run_id = run.id
    user = UserORM(
        id=uuid.uuid4(), name="op", email="op@example.com",
        password_hash="!", role="operador",
    )
    db.add(user)
    db.commit()
    alert = AlertORM(
        device_id=d.id, user_id=user.id, type="TEMPERATURE_EXCEEDED",
        message="warm", criticality=8.0, run_id=run.id,
    )
    db.add(alert)
    db.commit()
    db.refresh(run)
    assert [r.id for r in run.sensor_readings] == [reading.id]
    assert [a.id for a in run.alerts] == [alert.id]
    assert reading.experiment_run.id == run.id
    assert alert.experiment_run.id == run.id


def test_run_metrics_relationship(db):
    run = ExperimentRunRepository().create(db, scenario="WITHOUT_QOS")
    db.commit()
    ExperimentMetricRepository().append(
        db, run_id=run.id, metric_type="alerts_generated", value=2.0
    )
    db.commit()
    db.refresh(run)
    assert len(run.metrics) == 1
    assert run.metrics[0].run.id == run.id


# --- Historical compatibility -------------------------------------------------------

def test_legacy_null_run_id_valid(db):
    d = _device_with_sensors(db)
    reading = SensorReadingRepository().save(
        db,
        [
            NormalizedReading(device_code=d.code, device_type="cold_room", sensor_name="temperature", value=4.0, timestamp="2026-10-05T12:00:00+00:00", raw_value=4.0),
            NormalizedReading(device_code=d.code, device_type="cold_room", sensor_name="humidity", value=80.0, timestamp="2026-10-05T12:00:00+00:00", raw_value=80.0),
            NormalizedReading(device_code=d.code, device_type="cold_room", sensor_name="energy", value=1.0, timestamp="2026-10-05T12:00:00+00:00", raw_value="on"),
        ],
        d.id,
    )
    db.commit()
    assert reading.run_id is None
    user = UserORM(
        id=uuid.uuid4(), name="op", email="op2@example.com",
        password_hash="!", role="operador",
    )
    db.add(user)
    db.commit()
    alert = AlertORM(
        device_id=d.id, user_id=user.id, type="TEMPERATURE_EXCEEDED",
        message="warm", criticality=8.0,
    )
    db.add(alert)
    db.commit()
    assert alert.run_id is None
    assert alert.criticality == 8.0


def test_criticality_still_not_null(db):
    from app.database.infrastructure.models import AlertORM as _AlertORM

    assert not _AlertORM.__table__.c.criticality.nullable
