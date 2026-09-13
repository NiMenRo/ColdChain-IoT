import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import DeviceORM, UserORM
from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification
from app.database.application.persistence_service import PersistenceService
from app.database.infrastructure.session import get_db
from main import app

from sqlalchemy.pool import StaticPool
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine, future=True)
def _seed():
    s = Session()
    # clear if re-run
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    d1 = DeviceORM(code="CAVA-001", name="Cava", location="Lab", device_type="cold_room", status="active")
    d2 = DeviceORM(code="CAVA-002", name="Cava2", location="Lab", device_type="cold_room", status="active")
    u = UserORM(id=uuid.UUID("00000000-0000-0000-0000-000000000000"), name="system", email="system@coldchain.local", password_hash="!", role="system")
    s.add_all([d1, d2, u]); s.commit()
    s.close()
    # bundle
    ps = PersistenceService()
    s = Session()
    d1 = s.query(DeviceORM).filter_by(code="CAVA-001").first()
    u = s.query(UserORM).first()
    s.close()
    for i in range(3):
        readings = [NormalizedReading(device_code="CAVA-001", device_type="cold_room", sensor_name="temperature", value=5.0+i, timestamp=f"2026-09-02T0{i}:00:00+00:00", raw_value=5.0), NormalizedReading(device_code="CAVA-001", device_type="cold_room", sensor_name="humidity", value=80.0, timestamp=f"2026-09-02T0{i}:00:00+00:00", raw_value=80.0), NormalizedReading(device_code="CAVA-001", device_type="cold_room", sensor_name="energy", value=1.0, timestamp=f"2026-09-02T0{i}:00:00+00:00", raw_value="on")]
        tc = TrafficClassification(id=uuid.uuid4(), reading_id=uuid.uuid4(), criticality=5.0, priority="HIGH", queue="WFQ", classification_time=datetime.now(timezone.utc), timestamp=datetime.now(timezone.utc))
        from app.qos.domain import QoSMetric
        qos = QoSMetric(id=uuid.uuid4(), classification_id=tc.id, latency=0.1, packet_loss=0.0, throughput=100.0, pdr=100.0, jitter=0.01, timestamp=datetime.now(timezone.utc))
        from app.events.domain import Alert
        alert = Alert(id=uuid.uuid4(), device_id=d1.id, user_id=u.id, type="TEMPERATURE_EXCEEDED", message="test", criticality=5.0, acknowledged=False, created_at=datetime.now(timezone.utc))
        with Session() as s2:
            ps.persist_bundle(s2, readings=readings, device_id=d1.id, classification=tc, qos_metric=qos, alerts=[alert])
_seed()

def override_get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()
app.dependency_overrides[get_db] = override_get_db

def test_pagination():
    with TestClient(app) as c:
        r = c.get("/history/readings?page=1&per_page=2")
        assert r.status_code == 200
        assert r.json()["total"] == 3
        assert r.json()["count"] == 2
        r = c.get("/history/readings?page=2&per_page=2")
        assert r.json()["count"] == 1

def test_filter_device():
    with TestClient(app) as c:
        r = c.get("/history/readings?device_code=CAVA-001&page=1&per_page=10")
        assert r.json()["total"] == 3
        r = c.get("/history/readings?device_code=NOEXISTE&page=1&per_page=10")
        assert r.json()["total"] == 0
        assert r.json()["results"] == []

def test_404():
    with TestClient(app) as c:
        r = c.get(f"/history/readings/{uuid.uuid4()}")
        assert r.status_code == 404
        r = c.get(f"/history/alerts/{uuid.uuid4()}")
        assert r.status_code == 404

def test_400_per_page():
    with TestClient(app) as c:
        r = c.get("/history/readings?page=1&per_page=200")
        assert r.status_code in (400, 422)

def test_bundle():
    with TestClient(app) as c:
        s2 = Session()
        rid = s2.query(DeviceORM).first().id
        from app.database.infrastructure.models import SensorReadingORM
        sr = s2.query(SensorReadingORM).first()
        s2.close()
        r = c.get(f"/history/readings/{sr.id}/bundle")
        assert r.status_code == 200
        assert r.json()["sensor_reading"]["id"] == str(sr.id)

def test_trends():
    with TestClient(app) as c:
        r = c.get("/history/readings/trends?interval=hour")
        assert r.status_code == 200
        r = c.get("/history/qos/trends?interval=hour")
        assert r.status_code == 200

def test_summary():
    with TestClient(app) as c:
        r = c.get("/history/summary")
        assert r.status_code == 200
        assert r.json()["total_readings"] == 3

def test_predictions_empty():
    with TestClient(app) as c:
        r = c.get("/history/predictions?page=1&per_page=5")
        assert r.status_code == 200
        assert r.json()["total"] == 0

if __name__ == "__main__":
    test_pagination(); test_filter_device(); test_404(); test_400_per_page(); test_bundle(); test_trends(); test_summary(); test_predictions_empty()
    print("all history tests passed")
