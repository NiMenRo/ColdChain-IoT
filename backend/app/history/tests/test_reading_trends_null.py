"""TSK-059.3 — trends/history tolerate NULL (absent sensor, not zero)."""

from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.infrastructure.base import Base
from app.database.infrastructure.models import DeviceORM, SensorReadingORM
from app.history.infrastructure.reading_history_repository import ReadingHistoryRepository


def _db():
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
    return sessionmaker(bind=engine, future=True)()


def test_trends_partial_row_keeps_value_and_null():
    db = _db()
    d = DeviceORM(code="CAVA-001", name="C", location="L", device_type="cold_room", status="active")
    db.add(d)
    db.commit()
    db.add(
        SensorReadingORM(
            device_id=d.id,
            temperature=5.0,
            humidity=None,
            energy=None,
            timestamp=datetime(2026, 10, 5, 12, 10, tzinfo=timezone.utc),
        )
    )
    db.commit()
    rows = ReadingHistoryRepository().trends(db, device_code="CAVA-001", interval="hour")
    assert len(rows) == 1
    assert float(rows[0].avg_temp) == 5.0
    # absent sensor aggregates to NULL, never 0
    assert rows[0].avg_hum is None
    assert rows[0].min_hum is None
    assert rows[0].max_hum is None
    db.close()


def test_trends_avg_ignores_null_denominator():
    db = _db()
    d = DeviceORM(code="CAVA-001", name="C", location="L", device_type="cold_room", status="active")
    db.add(d)
    db.commit()
    db.add_all(
        [
            SensorReadingORM(device_id=d.id, temperature=4.0, humidity=80.0, energy="on",
                             timestamp=datetime(2026, 10, 5, 12, 10, tzinfo=timezone.utc)),
            SensorReadingORM(device_id=d.id, temperature=6.0, humidity=None, energy=None,
                             timestamp=datetime(2026, 10, 5, 12, 20, tzinfo=timezone.utc)),
        ]
    )
    db.commit()
    rows = ReadingHistoryRepository().trends(db, device_code="CAVA-001", interval="hour")
    assert len(rows) == 1
    assert float(rows[0].avg_temp) == 5.0
    assert float(rows[0].avg_hum) == 80.0  # NULL excluded, not averaged as 0
    db.close()


def test_history_list_serializes_null():
    from app.history.api.router import _serialize

    db = _db()
    d = DeviceORM(code="CAVA-001", name="C", location="L", device_type="cold_room", status="active")
    db.add(d)
    db.commit()
    db.add(
        SensorReadingORM(device_id=d.id, temperature=5.0, humidity=None, energy=None,
                         timestamp=datetime(2026, 10, 5, 12, 10, tzinfo=timezone.utc))
    )
    db.commit()
    total, items = ReadingHistoryRepository().list(db, device_code="CAVA-001")
    assert total == 1
    payload = _serialize(items[0])
    assert payload["temperature"] == 5.0
    assert payload["humidity"] is None
    assert payload["energy"] is None
    db.close()
