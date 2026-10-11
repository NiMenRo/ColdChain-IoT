"""Dynamic device mapping registration on POST /devices.

Creating a device via the API must register its code in the event
processing service without restarting the backend. When no event
service exists (isolated apps), creation must still succeed (201).
"""

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
from app.database.infrastructure.session import get_db
from app.devices.api import router
from app.events.application.event_processing_service import EventProcessingService
from app.events.domain import ThresholdConfig


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


def _service():
    return EventProcessingService(
        threshold_config=ThresholdConfig(
            min_temperature=0.0,
            max_temperature=4.0,
            min_humidity=85.0,
            max_humidity=90.0,
            allowed_energy_states=frozenset({"on"}),
        )
    )


class _Harness:
    def __init__(self, with_event_service: bool):
        self.engine = _engine()
        self.Session = sessionmaker(bind=self.engine, future=True)
        with self.Session() as db:
            user = AuthService().create_user(
                db, name="Admin", email="admin@example.com",
                password="pass-1234", role="admin",
            )
            db.commit()
            self.user_id = user.id
        app = FastAPI()
        app.include_router(router)
        if with_event_service:
            app.state.event_processing_service = _service()

        def _db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=self.user_id, email="admin@example.com", name="Admin",
            role="admin", is_active=True,
        )
        self.app = app
        self.client = TestClient(app)

    def post_device(self):
        return self.client.post("/devices", json={
            "name": "Cava",
            "location": "Lab",
            "device_type": "cold_room",
            "sensors": ["temperature"],
        })


def test_create_registers_mapping_without_restart():
    h = _Harness(with_event_service=True)
    r = h.post_device()
    assert r.status_code == 201, r.text
    code = r.json()["device"]["code"]
    assert code.startswith("CAVA-")
    service = h.app.state.event_processing_service
    assert service._device_mapping[code] == uuid.UUID(r.json()["device"]["id"])


def test_create_succeeds_without_event_service():
    h = _Harness(with_event_service=False)
    r = h.post_device()
    assert r.status_code == 201, r.text
