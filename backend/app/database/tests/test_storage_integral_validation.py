from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification
from app.database.application.persistence_service import PersistenceService
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import (
    AlertORM,
    DeviceORM,
    QoSMetricORM,
    SensorReadingORM,
    SystemConfigORM,
    TrafficClassificationORM,
    UserORM,
)
from app.database.infrastructure.repositories import (
    DeviceRepository,
    SystemConfigRepository,
    UserRepository,
)
from app.database.seed import SYSTEM_USER_ID
from app.events.domain import Alert, ThresholdConfig
from app.history.infrastructure.alert_history_repository import AlertHistoryRepository
from app.history.infrastructure.reading_history_repository import ReadingHistoryRepository
from app.qos.domain import QoSMetric
from simulator.devices import ColdRoom
from simulator.sensors import EnergyStatusSensor, HumiditySensor, TemperatureSensor


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _readings_from_registered_device(device: ColdRoom) -> list[NormalizedReading]:
    measurements = [sensor.read() for sensor in device.get_sensors()]
    timestamp = datetime.now(timezone.utc).isoformat()
    values = {
        "temperature": next(item.value for item in measurements if hasattr(item, "unit") and item.unit == "°C"),
        "humidity": next(item.value for item in measurements if hasattr(item, "unit") and item.unit == "%"),
        "energy": next(item.value for item in measurements if hasattr(item, "unit") and item.unit == "state"),
    }
    return [
        NormalizedReading(
            device_code=device.code,
            device_type="cold_room",
            sensor_name="temperature",
            value=float(values["temperature"]),
            timestamp=timestamp,
            raw_value=values["temperature"],
        ),
        NormalizedReading(
            device_code=device.code,
            device_type="cold_room",
            sensor_name="humidity",
            value=float(values["humidity"]),
            timestamp=timestamp,
            raw_value=values["humidity"],
        ),
        NormalizedReading(
            device_code=device.code,
            device_type="cold_room",
            sensor_name="energy",
            value=1.0 if values["energy"] == "on" else 0.0,
            timestamp=timestamp,
            raw_value=values["energy"],
        ),
    ]


def test_registered_device_sensor_flow_is_traceable_and_recoverable(db):
    device = ColdRoom(
        id="DEV-047-7",
        code="CAVA-047-7",
        name="Cava integral",
        location="Laboratorio",
    )
    device.add_sensor(TemperatureSensor(device=device, min_temperature=8.0, max_temperature=10.0))
    device.add_sensor(HumiditySensor(device=device, min_humidity=85.0, max_humidity=90.0))
    device.add_sensor(EnergyStatusSensor(device=device))

    persisted_device = DeviceRepository().create(
        db,
        code=device.code,
        name=device.name,
        location=device.location,
        device_type="cold_room",
        status="active",
    )
    system_user = UserORM(
        id=uuid.UUID(SYSTEM_USER_ID),
        name="system",
        email="system@coldchain.local",
        password_hash="!",
        role="system",
    )
    db.add(system_user)
    db.add(
        SystemConfigORM(
            id=uuid.uuid4(),
            min_temperature=0.0,
            max_temperature=4.0,
            min_humidity=85.0,
            max_humidity=90.0,
            qos_algorithm="wfq",
            qos_enabled=True,
        )
    )
    db.commit()

    persisted_config = SystemConfigRepository().get_current(db)
    threshold_config = ThresholdConfig.from_persisted_config(persisted_config)
    assert threshold_config.max_temperature == 4.0

    readings = _readings_from_registered_device(device)
    classification = TrafficClassification(
        id=uuid.uuid4(),
        reading_id=uuid.uuid4(),
        criticality=8.0,
        priority="high",
        queue="WFQ",
        classification_time=datetime.now(timezone.utc),
        timestamp=datetime.now(timezone.utc),
    )
    qos = QoSMetric(
        id=uuid.uuid4(),
        classification_id=classification.id,
        latency=0.5,
        packet_loss=0.0,
        throughput=256.0,
        pdr=100.0,
        jitter=0.1,
        timestamp=datetime.now(timezone.utc),
    )
    alert = Alert(
        id=uuid.uuid4(),
        device_id=persisted_device.id,
        user_id=system_user.id,
        type="TEMPERATURE_EXCEEDED",
        message="Temperature outside persisted threshold",
        criticality=8.0,
        acknowledged=False,
        created_at=datetime.now(timezone.utc),
    )

    result = PersistenceService().persist_bundle(
        db,
        readings=readings,
        device_id=persisted_device.id,
        classification=classification,
        qos_metric=qos,
        alerts=[alert],
    )
    db.commit()

    stored_reading = result["sensor_reading"]
    stored_classification = result["traffic_classification"]
    assert stored_reading.device_id == persisted_device.id
    assert stored_classification.reading_id == stored_reading.id
    assert result["qos_metric"].classification_id == stored_classification.id
    assert result["alerts"][0].device_id == persisted_device.id
    assert db.query(SensorReadingORM).count() == 1
    assert db.query(TrafficClassificationORM).count() == 1
    assert db.query(QoSMetricORM).count() == 1
    assert db.query(AlertORM).count() == 1

    bundle = ReadingHistoryRepository().get_bundle(db, stored_reading.id)
    assert bundle is not None
    assert bundle["device"].code == device.code
    assert bundle["sensor_reading"].id == stored_reading.id
    assert bundle["traffic_classification"].id == stored_classification.id
    assert len(bundle["qos_metrics"]) == 1
    assert len(bundle["alerts"]) == 1

    alert_total, alerts = AlertHistoryRepository().list(db, device_code=device.code)
    assert alert_total == 1
    assert alerts[0].id == alert.id


def test_unregistered_device_telemetry_is_rejected_without_persistence(db):
    readings = [
        NormalizedReading(
            device_code="UNKNOWN-CAVA",
            device_type="cold_room",
            sensor_name="temperature",
            value=10.0,
            timestamp="2026-09-14T00:00:00+00:00",
            raw_value=10.0,
        ),
        NormalizedReading(
            device_code="UNKNOWN-CAVA",
            device_type="cold_room",
            sensor_name="humidity",
            value=95.0,
            timestamp="2026-09-14T00:00:00+00:00",
            raw_value=95.0,
        ),
        NormalizedReading(
            device_code="UNKNOWN-CAVA",
            device_type="cold_room",
            sensor_name="energy",
            value=0.0,
            timestamp="2026-09-14T00:00:00+00:00",
            raw_value="off",
        ),
    ]

    with pytest.raises(ValueError, match="not registered"):
        from app.database.infrastructure.repositories import SensorReadingRepository

        SensorReadingRepository().save(db, readings, uuid.uuid4())

    assert db.query(SensorReadingORM).count() == 0
