"""TSK-059.3 — partial readings honoring DeviceSensor configuration."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.acquisition.normalizer import NormalizedReading
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import SensorReadingORM
from app.database.infrastructure.repositories import (
    DeviceRepository,
    DeviceSensorRepository,
    SensorReadingRepository,
)

TS = "2026-10-05T12:00:00+00:00"


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


def _device(db, code="CAVA-001", sensors=("temperature", "humidity", "energy")):
    d = DeviceRepository().create(
        db, code=code, name="Cava", location="Lab", device_type="cold_room", status="active"
    )
    db.commit()
    for s in sensors:
        DeviceSensorRepository().create(db, device_id=d.id, sensor_type=s)
    db.commit()
    return d


def _reading(code, name, value, ts=TS, raw=None):
    return NormalizedReading(
        device_code=code,
        device_type="cold_room",
        sensor_name=name,
        value=value,
        timestamp=ts,
        raw_value=raw if raw is not None else value,
    )


def test_full_bundle_unchanged(db):
    d = _device(db)
    obj = SensorReadingRepository().save(
        db,
        [_reading("CAVA-001", "temperature", 4.2), _reading("CAVA-001", "humidity", 72.0), _reading("CAVA-001", "energy", 1.0, raw="ON")],
        d.id,
    )
    db.commit()
    assert (obj.temperature, obj.humidity, obj.energy) == (4.2, 72.0, "on")


def test_two_sensors_missing_is_null(db):
    d = _device(db, sensors=("temperature", "humidity"))
    obj = SensorReadingRepository().save(
        db,
        [_reading("CAVA-001", "temperature", 5.2), _reading("CAVA-001", "humidity", 81.4)],
        d.id,
    )
    db.commit()
    assert (obj.temperature, obj.humidity, obj.energy) == (5.2, 81.4, None)


def test_single_sensor_two_nulls(db):
    d = _device(db, sensors=("temperature",))
    obj = SensorReadingRepository().save(db, [_reading("CAVA-001", "temperature", 5.2)], d.id)
    db.commit()
    assert (obj.temperature, obj.humidity, obj.energy) == (5.2, None, None)


def test_unconfigured_sensor_rejects_whole_bundle(db):
    d = _device(db, sensors=("temperature", "humidity"))
    with pytest.raises(ValueError, match="not configured"):
        SensorReadingRepository().save(
            db,
            [_reading("CAVA-001", "temperature", 5.2), _reading("CAVA-001", "humidity", 81.4), _reading("CAVA-001", "energy", 1.0, raw="on")],
            d.id,
        )
    db.rollback()
    assert db.query(SensorReadingORM).filter_by(device_id=d.id).count() == 0


def test_empty_readings_rejected(db):
    d = _device(db)
    with pytest.raises(ValueError):
        SensorReadingRepository().save(db, [], d.id)


def test_unknown_device_rejected(db):
    import uuid

    with pytest.raises(ValueError):
        SensorReadingRepository().save(db, [_reading("CAVA-001", "temperature", 5.2)], uuid.uuid4())


def test_energy_last_state_change_does_not_shift_timestamp(db):
    d = _device(db, sensors=("energy",))
    obj = SensorReadingRepository().save(
        db, [_reading("CAVA-001", "energy", 1.0, ts="2026-10-05T12:00:00+00:00", raw="on")], d.id
    )
    db.commit()
    # sqlite drops tzinfo on round-trip; compare wall time (group timestamp, not energy state time)
    assert obj.timestamp.replace(tzinfo=None).isoformat() == "2026-10-05T12:00:00"
    assert obj.energy == "on"


def test_delete_sensor_keeps_history(db):
    d = _device(db)
    SensorReadingRepository().save(
        db,
        [_reading("CAVA-001", "temperature", 4.0), _reading("CAVA-001", "humidity", 80.0), _reading("CAVA-001", "energy", 1.0, raw="on")],
        d.id,
    )
    db.commit()
    repo = DeviceSensorRepository()
    # keep 2 sensors so delete is allowed, history untouched
    temp = repo.get(db, d.id, "temperature")
    humidity = repo.get(db, d.id, "humidity")
    energy = repo.get(db, d.id, "energy")
    repo.delete(db, energy)
    db.commit()
    assert sorted(x.sensor_type for x in repo.list_by_device(db, d.id)) == ["humidity", "temperature"]
    assert db.query(SensorReadingORM).filter_by(device_id=d.id).count() == 1
    row = db.query(SensorReadingORM).filter_by(device_id=d.id).first()
    assert row.energy == "on"
    assert temp is not None and humidity is not None
