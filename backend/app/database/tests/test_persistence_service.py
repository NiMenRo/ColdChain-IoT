import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import DeviceORM, UserORM
from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification
from app.database.application.persistence_service import PersistenceService

def test_atomic_and_fk():
    from sqlalchemy import event
    from sqlalchemy.pool import StaticPool
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True)
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    s = Session()
    d = DeviceORM(code="CAVA-001", name="Cava", location="Lab", device_type="cold_room", status="active")
    u = UserORM(id=uuid.UUID("00000000-0000-0000-0000-000000000000"), name="system", email="system@coldchain.local", password_hash="!", role="system")
    s.add_all([d, u]); s.commit()
    ps = PersistenceService()
    readings = [NormalizedReading(device_code="CAVA-001", device_type="cold_room", sensor_name="temperature", value=5.0, timestamp="2026-09-02T00:00:00+00:00", raw_value=5.0), NormalizedReading(device_code="CAVA-001", device_type="cold_room", sensor_name="humidity", value=80.0, timestamp="2026-09-02T00:00:00+00:00", raw_value=80.0), NormalizedReading(device_code="CAVA-001", device_type="cold_room", sensor_name="energy", value=1.0, timestamp="2026-09-02T00:00:00+00:00", raw_value="on")]
    tc = TrafficClassification(id=uuid.uuid4(), reading_id=uuid.uuid4(), criticality=5.0, priority="HIGH", queue="WFQ", classification_time=datetime.now(timezone.utc), timestamp=datetime.now(timezone.utc))
    from app.qos.domain import QoSMetric
    qos = QoSMetric(id=uuid.uuid4(), classification_id=tc.id, latency=0.1, packet_loss=0.0, throughput=100.0, pdr=100.0, jitter=0.01, timestamp=datetime.now(timezone.utc))
    from app.events.domain import Alert
    alert = Alert(id=uuid.uuid4(), device_id=d.id, user_id=u.id, type="TEMPERATURE_EXCEEDED", message="test", criticality=5.0, acknowledged=False, created_at=datetime.now(timezone.utc))
    with Session() as s2:
        res = ps.persist_bundle(s2, readings=readings, device_id=d.id, classification=tc, qos_metric=qos, alerts=[alert])
        assert res["sensor_reading"].device_id == d.id
        assert res["traffic_classification"].reading_id == res["sensor_reading"].id
        assert res["alerts"][0].device_id == d.id
    # rollback on FK fail
    with Session() as s3:
        bad_alert = Alert(id=uuid.uuid4(), device_id=d.id, user_id=uuid.uuid4(), type="X", message="x", criticality=1.0, acknowledged=False, created_at=datetime.now(timezone.utc))
        try:
            ps.persist_bundle(s3, readings=readings, device_id=d.id, classification=TrafficClassification(id=uuid.uuid4(), reading_id=uuid.uuid4(), criticality=5.0, priority="HIGH", queue="WFQ", classification_time=datetime.now(timezone.utc), timestamp=datetime.now(timezone.utc)), qos_metric=None, alerts=[bad_alert])
            assert False, "should have raised"
        except Exception:
            s3.rollback()
            pass
    with Session() as s4:
        from app.database.infrastructure.models import SensorReadingORM
        # count should still be 1 (previous bundle) not 2, due to rollback
        assert s4.query(SensorReadingORM).count() == 1
    print("persistence tests passed")

if __name__ == "__main__":
    test_atomic_and_fk()
