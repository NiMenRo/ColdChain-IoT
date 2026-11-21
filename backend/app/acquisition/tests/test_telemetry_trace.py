import itertools
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.acquisition.pipeline as pipeline
import app.database.infrastructure.session as session_module
from app.acquisition.infrastructure.mqtt_subscriber import MQTTSubscriber
from app.acquisition.message_queue import MessageQueue
from app.acquisition.telemetry_trace import emission_trace, record_trace
from app.acquisition.tests.test_qos_dispatch_pipeline import (
    db_factory, _message, _pipeline_state, _seed_device,
)
from app.database.infrastructure.models import AlertORM, SensorReadingORM
from app.experiments import active


@pytest.fixture(autouse=True)
def no_active_run():
    active.clear_active_run()
    yield
    active.clear_active_run()


def _trace(run_id=None):
    return {
        "message_id": str(uuid4()), "producer_session_id": str(uuid4()),
        "sequence": 0, "run_id": run_id, "clock_domain": "isolated-test",
    }


@pytest.mark.parametrize("scenario", ["WITH_QOS", "WITHOUT_QOS"])
def test_emission_identity_survives_commit_and_replay_without_duplicating_readings(
    monkeypatch, tmp_path, db_factory, scenario,
):
    path = tmp_path / "backend.jsonl"
    monkeypatch.setenv("TELEMETRY_TRACE_FILE", str(path))
    monkeypatch.setenv("TELEMETRY_CLOCK_DOMAIN", "isolated-test")
    device_id, user_id = _seed_device(db_factory)
    monkeypatch.setattr(session_module, "SessionLocal", db_factory)
    state = _pipeline_state(device_id, user_id)
    state.notification_service = None
    message = _message(temperature=9.5)
    trace = _trace()
    message["payload"]["trace"] = trace
    message["scenario"] = scenario
    coordinator = pipeline._build_coordinator(state)
    pipeline._ingest_message(message, state, coordinator, itertools.count(),
                             datetime.now(timezone.utc))
    before = [json.loads(line) for line in path.read_text().splitlines()]
    assert all(row["event"] != "persisted" for row in before)
    while (item := coordinator.select_next()) is not None:
        assert str(item.source_message_id) == trace["message_id"]
        pipeline._process_work_item(item, state)
        coordinator.finish(success=True)
    pipeline._ingest_message(message, state, coordinator, itertools.count(3),
                             datetime.now(timezone.utc))
    while (item := coordinator.select_next()) is not None:
        assert pipeline._process_work_item(item, state) is None
        coordinator.finish(success=True)
    with db_factory() as db:
        readings = db.query(SensorReadingORM).all()
        assert len(readings) == 3
        assert all(str(row.source_message_id) == trace["message_id"] for row in readings)
        reading_ids = {row.id for row in readings}
        assert all(row.reading_id in reading_ids for row in db.query(AlertORM).all())
    rows = [json.loads(line) for line in path.read_text().splitlines()
            if json.loads(line)["event"] == "persisted"]
    assert len(rows) == 3
    assert all(row["event"] == "persisted" for row in rows)
    assert all(row["source_message_id"] == trace["message_id"] for row in rows)
    assert any(row["alerts"] for row in rows)


def test_receipt_measures_original_payload_bytes_including_non_ascii(monkeypatch, tmp_path):
    target = tmp_path / "backend.jsonl"
    monkeypatch.setenv("TELEMETRY_TRACE_FILE", str(target))
    queue = MessageQueue()
    subscriber = MQTTSubscriber(queue)
    payload = _message()["payload"]
    payload["trace"] = _trace()
    payload["note"] = "Cámara fría"
    wire = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    subscriber.on_message(None, None, SimpleNamespace(topic="unused", payload=wire))
    rows = [json.loads(line) for line in target.read_text().splitlines()]
    assert rows[0]["event"] == "received"
    assert rows[0]["size_bytes"] == len(wire)
    assert queue.pop()["trace"] == payload["trace"]


def test_delayed_message_is_not_reassigned_to_new_active_run(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEMETRY_TRACE_FILE", str(tmp_path / "backend.jsonl"))
    old_run, current_run = str(uuid4()), uuid4()
    active.set_active_run(current_run, "WITH_QOS")
    payload = _message()["payload"]
    payload["trace"] = _trace(old_run)
    queue = MessageQueue()
    subscriber = MQTTSubscriber(queue)
    subscriber.on_message(None, None, SimpleNamespace(
        topic="unused", payload=json.dumps(payload).encode(),
    ))
    assert len(queue) == 0
    assert queue.rejected == 1
    rows = [json.loads(line) for line in (tmp_path / "backend.jsonl").read_text().splitlines()]
    assert rows[0]["trace"]["run_id"] == old_run
    assert rows[-1]["event"] == "transport_rejected"


@pytest.mark.parametrize("value", [
    [], {"message_id": "not-uuid"},
    {"message_id": str(uuid4()), "producer_session_id": str(uuid4()), "sequence": True},
])
def test_invalid_emission_identity_is_rejected(value):
    with pytest.raises((ValueError, TypeError)):
        emission_trace({"trace": value})


def test_trace_disabled_has_no_files_or_fabricated_success(monkeypatch):
    monkeypatch.delenv("TELEMETRY_TRACE_FILE", raising=False)
    assert record_trace("persisted", work_id=str(uuid4())) is False


def test_sensor_timestamps_are_preserved_individually():
    from app.acquisition.normalizer import TelemetryNormalizer
    message = _message()
    message["payload"]["reading_timestamps"] = {
        "temperature": "2026-11-20T12:00:00.001+00:00",
        "humidity": "2026-11-20T12:00:00.002+00:00",
        "energy": "2026-11-20T12:00:00.003+00:00",
    }
    readings = TelemetryNormalizer().normalize(message)
    assert {reading.sensor_name: reading.timestamp for reading in readings} == (
        message["payload"]["reading_timestamps"]
    )


def test_failed_transaction_never_records_a_persisted_reading(monkeypatch, tmp_path, db_factory):
    target = tmp_path / "backend.jsonl"
    monkeypatch.setenv("TELEMETRY_TRACE_FILE", str(target))
    device_id, user_id = _seed_device(db_factory)
    monkeypatch.setattr(session_module, "SessionLocal", db_factory)
    state = _pipeline_state(device_id, user_id)
    state.notification_service = None

    def fail(*args, **kwargs):
        raise RuntimeError("controlled storage failure")

    monkeypatch.setattr(state.persistence_service, "persist_work_item", fail)
    message = _message(temperature=9.5)
    message["payload"]["trace"] = _trace()
    message["scenario"] = "WITH_QOS"
    coordinator = pipeline._build_coordinator(state)
    pipeline._ingest_message(message, state, coordinator, itertools.count(),
                             datetime.now(timezone.utc))
    item = coordinator.select_next()
    with pytest.raises(RuntimeError, match="controlled storage failure"):
        pipeline._process_work_item(item, state)
    assert all(json.loads(line)["event"] != "persisted"
               for line in target.read_text().splitlines())
    with db_factory() as db:
        assert db.query(SensorReadingORM).count() == 0
        assert db.query(AlertORM).count() == 0
