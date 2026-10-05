"""TSK-059.4 — repo/domain/DB integrity checks (no HTTP)."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import (
    DeviceORM,
    DeviceSensorORM,
    QoSMetricORM,
    SensorReadingORM,
    SystemConfigORM,
    TrafficClassificationORM,
)
from app.database.infrastructure.repositories import (
    DeviceRepository,
    SystemConfigRepository,
)
from app.qos.application.qos_metrics_service import QoSMetricsService
from app.qos.domain import QoSMetric


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


def _config(db):
    c = SystemConfigORM(
        min_temperature=0.0,
        max_temperature=4.0,
        min_humidity=85.0,
        max_humidity=90.0,
        qos_algorithm="wfq",
        qos_enabled=True,
    )
    db.add(c)
    db.commit()
    return c


def _tc(**over):
    base = dict(
        id=uuid.uuid4(),
        reading_id=uuid.uuid4(),
        criticality=5.0,
        priority="high",
        queue="WFQ",
        classification_time=datetime.now(timezone.utc),
        timestamp=datetime.now(timezone.utc),
    )
    base.update(over)
    return TrafficClassification(**base)


def _qos(**over):
    base = dict(
        id=uuid.uuid4(),
        classification_id=uuid.uuid4(),
        latency=0.1,
        packet_loss=0.0,
        throughput=100.0,
        pdr=100.0,
        jitter=0.01,
        timestamp=datetime.now(timezone.utc),
    )
    base.update(over)
    return QoSMetric(**base)


# --- SystemConfig repo -----------------------------------------------------

def test_system_config_update_valid(db):
    c = _config(db)
    out = SystemConfigRepository().update(db, c, max_temperature=6.0)
    db.commit()
    assert out.max_temperature == 6.0
    assert out.qos_algorithm == "wfq"  # untouched


def test_system_config_update_rejects_inverted(db):
    c = _config(db)
    with pytest.raises(ValueError):
        SystemConfigRepository().update(db, c, min_temperature=10.0)
    db.rollback()
    with pytest.raises(ValueError):
        SystemConfigRepository().update(db, c, min_humidity=95.0)
    db.rollback()


def test_system_config_update_rejects_unknown_field(db):
    c = _config(db)
    with pytest.raises(ValueError):
        SystemConfigRepository().update(db, c, qos_algorithm="fifo")
    db.rollback()
    with pytest.raises(ValueError):
        SystemConfigRepository().update(db, c, qos_enabled=False)
    db.rollback()


def test_system_config_check_constraint(db):
    from sqlalchemy import text

    _config(db)
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "UPDATE system_configs SET min_temperature = 10.0 "
                "WHERE max_temperature = 4.0"
            )
        )
    db.rollback()


# --- TrafficClassification domain + DB -------------------------------------

def test_criticality_out_of_range_rejected_by_domain():
    with pytest.raises(ValueError):
        _tc(criticality=2.9)
    with pytest.raises(ValueError):
        _tc(criticality=9.1)


def test_priority_case_normalized_but_unknown_rejected():
    assert _tc(priority="HIGH").priority == "high"
    with pytest.raises(ValueError):
        _tc(priority="urgent")


def test_queue_rr_rejected_by_domain():
    with pytest.raises(ValueError):
        _tc(queue="RR")
    assert _tc(queue="Round Robin").queue == "Round Robin"


def test_tc_check_constraints(db):
    db.add(
        TrafficClassificationORM(
            id=uuid.uuid4(),
            reading_id=uuid.uuid4(),
            criticality=100.0,
            priority="high",
            queue="WFQ",
            classification_time=datetime.now(timezone.utc),
            timestamp=datetime.now(timezone.utc),
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    db.add(
        TrafficClassificationORM(
            id=uuid.uuid4(),
            reading_id=uuid.uuid4(),
            criticality=5.0,
            priority="urgent",
            queue="WFQ",
            classification_time=datetime.now(timezone.utc),
            timestamp=datetime.now(timezone.utc),
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# --- QoS domain + formulas + DB --------------------------------------------

def test_qos_out_of_range_rejected_by_domain():
    with pytest.raises(ValueError):
        _qos(pdr=101.0)
    with pytest.raises(ValueError):
        _qos(packet_loss=-5.0)
    with pytest.raises(ValueError):
        _qos(latency=-1.0)


def test_pdr_loss_received_gt_sent_rejected():
    svc = QoSMetricsService()
    with pytest.raises(ValueError):
        svc.calculate_pdr(10, 12)
    with pytest.raises(ValueError):
        svc.calculate_packet_loss(10, 12)


def test_qos_check_constraints(db):
    db.add(
        QoSMetricORM(
            id=uuid.uuid4(),
            classification_id=uuid.uuid4(),
            latency=-1.0,
            packet_loss=0.0,
            throughput=100.0,
            pdr=100.0,
            jitter=0.0,
            timestamp=datetime.now(timezone.utc),
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    db.add(
        QoSMetricORM(
            id=uuid.uuid4(),
            classification_id=uuid.uuid4(),
            latency=0.1,
            packet_loss=0.0,
            throughput=100.0,
            pdr=120.0,
            jitter=0.0,
            timestamp=datetime.now(timezone.utc),
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# --- energy -----------------------------------------------------------------

def test_energy_numeric_rejected_at_save(db):
    d = DeviceRepository().create(
        db, code="CAVA-E", name="C", location="L", device_type="cold_room", status="active"
    )
    db.commit()
    db.add(DeviceSensorORM(device_id=d.id, sensor_type="energy"))
    db.commit()
    from app.database.infrastructure.repositories import SensorReadingRepository

    with pytest.raises(ValueError, match="energy"):
        SensorReadingRepository().save(
            db,
            [
                NormalizedReading(
                    device_code="CAVA-E",
                    device_type="cold_room",
                    sensor_name="energy",
                    value=1.0,
                    timestamp="2026-10-05T12:00:00+00:00",
                    raw_value=1,
                )
            ],
            d.id,
        )
    db.rollback()


def test_energy_check_constraint(db):
    d = DeviceORM(code="CAVA-X", name="C", location="L", device_type="cold_room", status="active")
    db.add(d)
    db.commit()
    db.add(
        SensorReadingORM(
            device_id=d.id,
            temperature=4.0,
            humidity=80.0,
            energy="standby",
            timestamp=datetime.now(timezone.utc),
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    # NULL remains valid (sensor not enabled)
    db.add(
        SensorReadingORM(
            device_id=d.id,
            temperature=4.0,
            humidity=None,
            energy=None,
            timestamp=datetime.now(timezone.utc),
        )
    )
    db.flush()
