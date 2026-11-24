from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from simulator import main
from simulator.database import session


def test_normal_devices_follow_persisted_thresholds(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool)
    factory = sessionmaker(bind=engine)
    device_id = str(uuid4())
    with engine.begin() as db:
        db.execute(text("CREATE TABLE devices (id TEXT, code TEXT, name TEXT, location TEXT, device_type TEXT, status TEXT, registration_date TEXT)"))
        db.execute(text("CREATE TABLE device_sensors (device_id TEXT, sensor_type TEXT)"))
        db.execute(text("CREATE TABLE system_configs (id INTEGER, min_temperature REAL, max_temperature REAL, min_humidity REAL, max_humidity REAL)"))
        db.execute(text("INSERT INTO devices VALUES (:id, 'D-1', 'Prueba', 'Laboratorio', 'refrigerated_showcase', 'maintenance', '2026-01-01')"), {"id": device_id})
        db.execute(text("INSERT INTO device_sensors VALUES (:id, 'temperature'), (:id, 'humidity'), (:id, 'energy')"), {"id": device_id})
        db.execute(text("INSERT INTO system_configs VALUES (1, 0, 4, 85, 90)"))
    monkeypatch.setattr(session, "SessionLocal", factory)

    devices = main.load_devices("normal")
    assert len(devices) == 1
    readings = [sensor.read() for sensor in devices[0].get_sensors()]
    assert 0 <= readings[0].value <= 4
    assert 85 <= readings[1].value <= 90
    assert readings[2].value == "on"
