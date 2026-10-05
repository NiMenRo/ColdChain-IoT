"""TSK-059.8 — devices API: create/list/detail/replace sensors, RBAC, integrity."""

import sys
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.auth.service import AuthService
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import AuditLogORM, DeviceORM, DeviceSensorORM, SensorReadingORM
from app.database.infrastructure.session import get_db
from app.devices.api import router

FULL = {"temperature": 4.0, "humidity": 80.0, "energy": "on"}


def _engine():
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
    return engine


class _Harness:
    def __init__(self, role="admin"):
        self.engine = _engine()
        self.Session = sessionmaker(bind=self.engine, future=True)
        with self.Session() as db:
            user = AuthService().create_user(
                db, name=role.title(), email=f"{role}@example.com",
                password="pass-1234", role=role,
            )
            db.commit()
            self.user_id = user.id
        app = FastAPI()
        app.include_router(router)

        def _db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=self.user_id, email=f"{role}@example.com", name=role.title(),
            role=role, is_active=True,
        )
        self.client = TestClient(app)

    def post_device(self, **over):
        body = {
            "code": f"DEV-{uuid.uuid4().hex[:6]}",
            "name": "Cava",
            "location": "Lab",
            "device_type": "cold_room",
            "sensors": ["temperature", "humidity", "energy"],
        }
        body.update(over)
        return self.client.post("/devices", json=body)


def test_create_one_and_three_sensors():
    h = _Harness()
    r = h.post_device(sensors=["temperature"])
    assert r.status_code == 201, r.text
    assert r.json()["sensors"] == ["temperature"]
    r = h.post_device(sensors=["temperature", "humidity", "energy"])
    assert r.status_code == 201, r.text
    assert r.json()["sensors"] == ["energy", "humidity", "temperature"]
    with h.Session() as db:
        assert db.query(DeviceORM).count() == 2
        assert db.query(DeviceSensorORM).count() == 4
        rows = db.query(AuditLogORM).filter_by(action="device.create").all()
        assert len(rows) == 2
        assert all(row.old_value is None and row.new_value is None for row in rows)


def test_create_empty_sensors_400():
    h = _Harness()
    r = h.post_device(sensors=[])
    assert r.status_code == 400, r.text
    with h.Session() as db:
        assert db.query(DeviceORM).count() == 0


def test_create_invalid_sensor_422():
    h = _Harness()
    r = h.post_device(sensors=["pressure"])
    assert r.status_code == 422, r.text
    with h.Session() as db:
        assert db.query(DeviceORM).count() == 0


def test_create_duplicate_sensors_400():
    h = _Harness()
    r = h.post_device(sensors=["temperature", "Temperature "])
    assert r.status_code == 400, r.text
    with h.Session() as db:
        assert db.query(DeviceORM).count() == 0


def test_create_duplicate_code_409_no_orphans():
    h = _Harness()
    assert h.post_device(code="DUP-001").status_code == 201
    r = h.post_device(code="DUP-001", sensors=["temperature"])
    assert r.status_code == 409, r.text
    with h.Session() as db:
        assert db.query(DeviceORM).count() == 1
        # the failed request left no device and no sensors behind
        assert db.query(DeviceSensorORM).count() == 3


def test_list_pagination_filters_search():
    h = _Harness()
    h.post_device(code="CAVA-A", device_type="cold_room", status="active")
    h.post_device(code="VIT-B", device_type="refrigerated_showcase", status="maintenance")
    body = h.client.get("/devices", params={"page": 1, "per_page": 1}).json()
    assert body["total"] == 2 and body["count"] == 1 and body["page"] == 1
    body = h.client.get("/devices", params={"device_type": "cold_room"}).json()
    assert body["total"] == 1
    body = h.client.get("/devices", params={"search": "vit"}).json()
    assert body["total"] == 1
    body = h.client.get("/devices", params={"status": "active"}).json()
    assert body["total"] == 1


def test_detail_and_404():
    h = _Harness()
    device_id = h.post_device(sensors=["humidity"]).json()["device"]["id"]
    body = h.client.get(f"/devices/{device_id}").json()
    assert body["device"]["id"] == device_id
    assert body["sensors"] == ["humidity"]
    assert h.client.get(f"/devices/{uuid.uuid4()}").status_code == 404


def test_replace_add_remove_keep():
    h = _Harness()
    device_id = h.post_device(sensors=["temperature", "humidity"]).json()["device"]["id"]
    r = h.client.put(f"/devices/{device_id}/sensors", json={"sensors": ["temperature", "energy"]})
    assert r.status_code == 200, r.text
    assert r.json()["sensors"] == ["energy", "temperature"]
    with h.Session() as db:
        rows = db.query(AuditLogORM).filter_by(action="device.sensors_update").all()
        assert len(rows) == 1
        assert rows[0].resource == f"devices/{device_id}"
        import json as _json
        assert _json.loads(rows[0].old_value) == {"sensors": ["humidity", "temperature"]}
        assert _json.loads(rows[0].new_value) == {"sensors": ["energy", "temperature"]}


def test_replace_empty_and_last_and_404():
    h = _Harness()
    device_id = h.post_device(sensors=["temperature"]).json()["device"]["id"]
    assert h.client.put(f"/devices/{device_id}/sensors", json={"sensors": []}).status_code == 400
    assert h.client.put(f"/devices/{uuid.uuid4()}/sensors", json={"sensors": ["temperature"]}).status_code == 404
    body = h.client.get(f"/devices/{device_id}").json()
    assert body["sensors"] == ["temperature"]


def test_replace_keeps_history():
    from datetime import datetime, timezone

    h = _Harness()
    device_id = h.post_device(sensors=["temperature", "humidity"]).json()["device"]["id"]
    with h.Session() as db:
        device = db.query(DeviceORM).filter_by(id=uuid.UUID(device_id)).first()
        db.add(
            SensorReadingORM(
                device_id=device.id, temperature=4.0, humidity=80.0, energy=None,
                timestamp=datetime.now(timezone.utc),
            )
        )
        db.commit()
    r = h.client.put(f"/devices/{device_id}/sensors", json={"sensors": ["temperature"]})
    assert r.status_code == 200, r.text
    with h.Session() as db:
        readings = db.query(SensorReadingORM).all()
        assert len(readings) == 1
        assert (readings[0].temperature, readings[0].humidity) == (4.0, 80.0)


def test_rbac_matrix():
    admin = _Harness(role="admin")
    device_id = admin.post_device(sensors=["temperature"]).json()["device"]["id"]
    for role in ("supervisor", "operador", "auditor"):
        h = _Harness(role=role)
        assert h.post_device(sensors=["temperature"]).status_code == 403, role
        # 403 precedes 404: RBAC runs before the device lookup
        assert h.client.put(
            f"/devices/{uuid.uuid4()}/sensors", json={"sensors": ["temperature"]}
        ).status_code == 403, role
    # admin can still operate
    assert admin.client.put(
        f"/devices/{device_id}/sensors", json={"sensors": ["humidity"]}
    ).status_code == 200
    # unauthenticated
    h = _Harness()
    from fastapi import FastAPI as _FastAPI

    app = _FastAPI()
    app.include_router(router)

    def _db():
        db = h.Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    anon = TestClient(app)
    assert anon.post("/devices", json={}).status_code in (401, 403, 422)
    assert anon.get("/devices").status_code in (401, 403)


def test_get_requires_auth_but_allows_any_role():
    h = _Harness(role="auditor")
    assert h.client.get("/devices").status_code == 200
