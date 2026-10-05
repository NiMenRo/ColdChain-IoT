import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.infrastructure.base import Base
from app.database.infrastructure.models import DeviceORM, SensorReadingORM
from app.database.infrastructure.repositories import DeviceRepository, DeviceSensorRepository
from app.database.seed import DEVICE_SEED, seed_device_sensors, seed_devices


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


def _make_device(db, code="CAVA-001"):
    repo = DeviceRepository()
    d = repo.create(db, code=code, name="Cava", location="Lab", device_type="cold_room", status="active")
    db.commit()
    return d


def test_create_valid_sensor(db):
    device = _make_device(db)
    repo = DeviceSensorRepository()
    s = repo.create(db, device_id=device.id, sensor_type="temperature")
    db.commit()
    assert s.device_id == device.id
    assert s.sensor_type == "temperature"
    assert repo.get(db, device.id, "temperature").id == s.id
    assert [x.sensor_type for x in repo.list_by_device(db, device.id)] == ["temperature"]


def test_create_normalizes_sensor_type(db):
    device = _make_device(db)
    repo = DeviceSensorRepository()
    s = repo.create(db, device_id=device.id, sensor_type="  Humidity ")
    db.commit()
    assert s.sensor_type == "humidity"


def test_create_invalid_sensor_type(db):
    device = _make_device(db)
    repo = DeviceSensorRepository()
    with pytest.raises(ValueError):
        repo.create(db, device_id=device.id, sensor_type="pressure")
    with pytest.raises(ValueError):
        repo.create(db, device_id=device.id, sensor_type="  ")


def test_create_unknown_device(db):
    repo = DeviceSensorRepository()
    with pytest.raises(ValueError):
        repo.create(db, device_id=uuid.uuid4(), sensor_type="temperature")


def test_duplicate_sensor_uses_db_unique(db):
    device = _make_device(db)
    repo = DeviceSensorRepository()
    repo.create(db, device_id=device.id, sensor_type="temperature")
    db.commit()
    with pytest.raises(IntegrityError):
        repo.create(db, device_id=device.id, sensor_type="temperature")
        db.flush()
    db.rollback()
    assert len(repo.list_by_device(db, device.id)) == 1


def test_fk_enforced(db):
    # create() guards unknown devices with ValueError; prove the DB-level
    # FK with a raw row bypassing the repository guard.
    from app.database.infrastructure.models import DeviceSensorORM

    db.add(DeviceSensorORM(device_id=uuid.uuid4(), sensor_type="energy"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_cannot_delete_last_sensor(db):
    device = _make_device(db)
    repo = DeviceSensorRepository()
    s = repo.create(db, device_id=device.id, sensor_type="temperature")
    db.commit()
    with pytest.raises(ValueError):
        repo.delete(db, s)
    assert len(repo.list_by_device(db, device.id)) == 1


def test_delete_keeps_history(db):
    from datetime import datetime, timezone

    device = _make_device(db)
    repo = DeviceSensorRepository()
    repo.create(db, device_id=device.id, sensor_type="temperature")
    repo.create(db, device_id=device.id, sensor_type="humidity")
    db.commit()
    # historical reading with humidity data
    db.add(
        SensorReadingORM(
            device_id=device.id,
            temperature=4.0,
            humidity=80.0,
            energy="on",
            timestamp=datetime.now(timezone.utc),
        )
    )
    db.commit()
    temp = repo.get(db, device.id, "temperature")
    repo.delete(db, temp)
    db.commit()
    assert [x.sensor_type for x in repo.list_by_device(db, device.id)] == ["humidity"]
    assert db.query(SensorReadingORM).filter_by(device_id=device.id).count() == 1


def test_seed_devices_get_three_sensors_idempotent(db):
    assert seed_devices(db) == len(DEVICE_SEED)
    assert seed_device_sensors(db) == len(DEVICE_SEED) * 3
    # second run inserts nothing
    assert seed_devices(db) == 0
    assert seed_device_sensors(db) == 0
    repo = DeviceSensorRepository()
    for d in DEVICE_SEED:
        device = db.query(DeviceORM).filter_by(code=d["code"]).first()
        assert device is not None
        assert sorted(x.sensor_type for x in repo.list_by_device(db, device.id)) == [
            "energy",
            "humidity",
            "temperature",
        ]


def test_repos_do_not_commit(db):
    device = _make_device(db)
    repo = DeviceSensorRepository()
    repo.create(db, device_id=device.id, sensor_type="energy")
    assert repo.get(db, device.id, "energy") is not None
    db.rollback()
    assert repo.get(db, device.id, "energy") is None
