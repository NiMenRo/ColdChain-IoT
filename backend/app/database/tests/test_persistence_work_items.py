"""Dispatch-v2 persistence is one committed row per selected sensor."""

from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification
from app.database.application.persistence_service import PersistenceService
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import (
    AlertORM,
    DeviceORM,
    DeviceSensorORM,
    SensorReadingORM,
    TrafficClassificationORM,
    UserORM,
)
from app.events.domain import Alert
from app.qos.domain.work_item import WorkItem


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    device = DeviceORM(
        code="CAVA-DISPATCH", name="Cava", location="Lab",
        device_type="cold_room", status="active",
    )
    user = UserORM(
        name="System", email="system@dispatch.local", password_hash="!",
        role="system",
    )
    session.add_all([device, user])
    session.flush()
    session.add_all(
        DeviceSensorORM(device_id=device.id, sensor_type=sensor)
        for sensor in ("temperature", "humidity", "energy")
    )
    session.commit()
    yield session, device, user
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _work(
    *,
    sensor_name: str,
    value: float,
    raw_value: str | float,
    priority: str | None,
    source_message_id: uuid.UUID,
    run_id: uuid.UUID | None = None,
) -> WorkItem:
    timestamp = "2026-11-19T12:00:00+00:00"
    reading = NormalizedReading(
        device_code="CAVA-DISPATCH",
        device_type="cold_room",
        sensor_name=sensor_name,
        value=value,
        timestamp=timestamp,
        raw_value=raw_value,
    )
    classification = None
    if priority is not None:
        queue = {"low": "FIFO", "medium": "Round Robin", "high": "WFQ"}[priority]
        classification = TrafficClassification(
            id=uuid.uuid4(),
            reading_id=uuid.uuid4(),
            criticality={"low": 3.0, "medium": 4.0, "high": 5.0}[priority],
            priority=priority,
            queue=queue,
            classification_time=datetime.now(timezone.utc),
            timestamp=datetime.fromisoformat(timestamp),
        )
    return WorkItem.from_reading(
        reading,
        source_message_id=source_message_id,
        sequence=0,
        scenario="WITH_QOS" if classification is not None else "WITHOUT_QOS",
        run_id=run_id,
        classification=classification,
        admitted_at=datetime.now(timezone.utc),
        admitted_monotonic=1.0,
    )


def _alert(device_id, user_id):
    return Alert(
        id=uuid.uuid4(),
        device_id=device_id,
        user_id=user_id,
        type="TEMPERATURE_EXCEEDED",
        message="dispatch test",
        criticality=5.0,
        acknowledged=False,
        created_at=datetime.now(timezone.utc),
    )


def test_three_sibling_work_items_persist_independently_with_own_classifications_and_alerts(db):
    session, device, user = db
    source = uuid.uuid4()
    service = PersistenceService()
    works = [
        _work(sensor_name="temperature", value=9.5, raw_value=9.5, priority="high", source_message_id=source),
        _work(sensor_name="humidity", value=82.0, raw_value=82.0, priority="medium", source_message_id=source),
        _work(sensor_name="energy", value=1.0, raw_value="on", priority="low", source_message_id=source),
    ]

    results = [
        service.persist_work_item(
            session,
            work_item=work,
            device_id=device.id,
            alerts=[_alert(device.id, user.id)],
        )
        for work in works
    ]
    session.commit()

    rows = session.query(SensorReadingORM).order_by(SensorReadingORM.sensor_name).all()
    assert len(rows) == 3
    assert {(row.sensor_name, row.source_message_id, row.processing_version) for row in rows} == {
        ("temperature", source, 2),
        ("humidity", source, 2),
        ("energy", source, 2),
    }
    assert {(row.temperature, row.humidity, row.energy) for row in rows} == {
        (9.5, None, None), (None, 82.0, None), (None, None, "on")
    }
    assert {
        (result["traffic_classification"].reading_id, result["traffic_classification"].priority)
        for result in results
    } == {(work.id, work.priority) for work in works}
    assert {
        (alert.reading_id, alert.device_id) for alert in session.query(AlertORM).all()
    } == {(work.id, device.id) for work in works}


def test_without_qos_work_item_has_no_qos_rows_and_replay_is_idempotent(db):
    session, device, user = db
    work = _work(
        sensor_name="temperature", value=9.5, raw_value=9.5, priority=None,
        source_message_id=uuid.uuid4(),
    )
    service = PersistenceService()
    first = service.persist_work_item(
        session, work_item=work, device_id=device.id, alerts=[_alert(device.id, user.id)]
    )
    session.commit()
    replay = service.persist_work_item(
        session, work_item=work, device_id=device.id, alerts=[_alert(device.id, user.id)]
    )

    assert first["sensor_reading"].id == replay["sensor_reading"].id == work.id
    assert replay["traffic_classification"] is None
    assert session.query(SensorReadingORM).count() == 1
    assert session.query(TrafficClassificationORM).count() == 0
    assert session.query(AlertORM).count() == 1


def test_failed_alert_rolls_back_the_selected_work_item(db):
    session, device, _ = db
    work = _work(
        sensor_name="temperature", value=9.5, raw_value=9.5, priority="high",
        source_message_id=uuid.uuid4(),
    )
    bad_alert = _alert(device.id, uuid.uuid4())

    with pytest.raises(Exception):
        PersistenceService().persist_work_item(
            session, work_item=work, device_id=device.id, alerts=[bad_alert]
        )
    session.rollback()

    assert session.query(SensorReadingORM).filter_by(id=work.id).count() == 0
    assert session.query(TrafficClassificationORM).count() == 0
    assert session.query(AlertORM).count() == 0
