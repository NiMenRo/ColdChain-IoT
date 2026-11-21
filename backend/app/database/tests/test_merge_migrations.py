"""Both already-deployed heads must upgrade without losing either feature."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.database.infrastructure.models import DeviceORM, SensorReadingORM


@pytest.mark.parametrize("starting_revision", [None, "b4d6e8a2c901", "f3a8b2c7d901"])
def test_qos_password_reset_merge_has_one_head_and_preserves_data(
    monkeypatch, tmp_path, starting_revision
):
    backend = Path(__file__).resolve().parents[3]
    config = Config(str(backend / "alembic.ini"))
    url = f"sqlite:///{(tmp_path / 'merged.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    # env.py's CLI logging setup must not disable loggers used by subsequent
    # application tests (e.g. assertions about unknown-device warnings).
    monkeypatch.setattr("logging.config.fileConfig", lambda *args, **kwargs: None)
    assert ScriptDirectory.from_config(config).get_heads() == ["a7c1e9d4b260"]
    device_id, reading_id = uuid4(), uuid4()
    if starting_revision:
        command.upgrade(config, starting_revision)
        engine = create_engine(url)
        try:
            with Session(engine) as db, db.begin():
                db.add(DeviceORM(
                    id=device_id, code="MERGE-001", name="Existing", location="Lab",
                    device_type="cold_room", status="active",
                ))
                db.flush()
                if starting_revision == "b4d6e8a2c901":
                    from datetime import datetime, timezone

                    db.add(SensorReadingORM(
                        id=reading_id, device_id=device_id, temperature=9.5,
                        timestamp=datetime.now(timezone.utc), sensor_name="temperature",
                        source_message_id=uuid4(), processing_version=2,
                    ))
        finally:
            engine.dispose()
    command.upgrade(config, "head")
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        assert "password_reset_tokens" in inspector.get_table_names()
        assert {"sensor_name", "processing_version", "source_message_id"} <= {
            col["name"] for col in inspector.get_columns("sensor_readings")
        }
        assert {"queue_wait_ms", "service_time_ms", "persisted_at"} <= {
            col["name"] for col in inspector.get_columns("qos_metrics")
        }
        criticality = next(
            col for col in inspector.get_columns("alerts") if col["name"] == "criticality"
        )
        assert criticality["nullable"] is True
        with Session(engine) as db:
            assert db.execute(text("SELECT version_num FROM alembic_version")).scalars().all() == ["a7c1e9d4b260"]
            if starting_revision:
                assert db.get(DeviceORM, device_id).code == "MERGE-001"
            if starting_revision == "b4d6e8a2c901":
                reading = db.get(SensorReadingORM, reading_id)
                assert (reading.temperature, reading.processing_version) == (9.5, 2)
    finally:
        engine.dispose()
