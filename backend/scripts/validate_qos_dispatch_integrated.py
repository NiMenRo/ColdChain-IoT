"""Offline comparison using the real ingestion/dispatch path and isolated SQLite.

Prints a JSON report. Never connects to MQTT, PostgreSQL or notification
channels. Times are observations, not deterministic benchmark predictions.
"""
from __future__ import annotations

import itertools
import json
import logging
import os
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["COLDCHAIN_SIM_WORKER_ENABLED"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import app.acquisition.pipeline as pipeline
import app.database.infrastructure.session as session_module
from app.database.application.persistence_service import PersistenceService
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import (
    AlertORM, DeviceORM, DeviceSensorORM, ExperimentMetricORM, ExperimentRunORM,
    QoSMetricORM, SensorReadingORM, TrafficClassificationORM, UserORM,
)
from app.events.application.event_processing_service import EventProcessingService
from app.events.domain import ThresholdConfig
from app.qos.application.dispatcher import DispatchCoordinator
from app.qos.application.traffic_planning_service import TrafficPlanningService

logging.disable(logging.CRITICAL)
LABELS = {"temperature": "high", "humidity": "medium", "energy": "low"}


def run_case(root: Path, scenario: str, messages: int, repetition: int) -> dict:
    engine = create_engine(f"sqlite:///{(root / f'{scenario}-{messages}-{repetition}.db').as_posix()}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    session_module.SessionLocal = factory
    run_id, device_id, user_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    with factory.begin() as db:
        db.add(DeviceORM(id=device_id, code="CAVA-001", name="Cava",
                         location="Laboratorio", device_type="cold_room", status="active"))
        db.add(UserORM(id=user_id, name="system", email="system@coldchain.local",
                       password_hash="!", role="system", is_active=True))
        db.add(ExperimentRunORM(id=run_id, scenario=scenario, started_at=now))
        db.flush()
        db.add_all(DeviceSensorORM(device_id=device_id, sensor_type=sensor)
                   for sensor in LABELS)

    thresholds = ThresholdConfig(min_temperature=0, max_temperature=4,
                                 min_humidity=85, max_humidity=90,
                                 allowed_energy_states=frozenset({"on"}))
    state = SimpleNamespace(
        classifications=[], events=[], alerts=[], enriched_events=[], notifications=[],
        persistence_service=PersistenceService(),
        event_processing_service=EventProcessingService(
            thresholds, device_mapping={"CAVA-001": device_id}, user_id=user_id,
        ),
        notification_service=None,
    )
    coordinator = DispatchCoordinator(TrafficPlanningService(), capacity=messages * 3)
    sequence = itertools.count()
    ingest_started = time.monotonic()
    for _ in range(messages):
        received = datetime.now(timezone.utc)
        payload = {"device_code": "CAVA-001", "device_type": "cold_room",
                   "temperature": 9.5, "humidity": 82.0, "energy": "on",
                   "timestamp": received.isoformat()}
        message = {"topic": "coldchain/device/CAVA-001/telemetry", "payload": payload,
                   "device_origin": {"device_code": "CAVA-001", "device_type": "cold_room"},
                   "scenario": scenario, "run_id": str(run_id),
                   "received_at": received.isoformat(), "received_monotonic": time.monotonic()}
        pipeline._record_run_metrics(run_id, [("messages_received", 1.0, received)])
        pipeline._ingest_message(message, state, coordinator, sequence, received)
    ingest_ms = (time.monotonic() - ingest_started) * 1000
    trace = []
    original = pipeline._process_work_item

    def record_attention(item, app_state):
        selected = time.monotonic()
        entry = {"sequence": item.sequence, "sensor": item.sensor_name,
                 "evaluation_class": LABELS[item.sensor_name],
                 "dispatch_priority": item.priority,
                 "queue_wait_ms": max(0.0, (selected - item.admitted_monotonic) * 1000)}
        trace.append(entry)
        try:
            committed = original(item, app_state)
            entry["committed"] = committed is not None
            return committed
        finally:
            entry["attention_ms"] = (time.monotonic() - selected) * 1000

    pipeline._process_work_item = record_attention
    try:
        coordinator.close_admission()
        pipeline._attention_loop(coordinator, state, threading.Event())
    finally:
        pipeline._process_work_item = original

    with factory() as db:
        readings = db.query(SensorReadingORM).filter_by(run_id=run_id).all()
        classifications = db.query(TrafficClassificationORM).count()
        qos_rows = db.query(QoSMetricORM).count()
        alerts = db.query(AlertORM).filter_by(run_id=run_id).all()
        metrics = Counter()
        for metric in db.query(ExperimentMetricORM).filter_by(run_id=run_id):
            if metric.metric_type in {"messages_received", "readings_admitted",
                                      "readings_persisted", "readings_failed", "alerts_generated"}:
                metrics[metric.metric_type] += metric.value
        assert len(readings) == messages * 3
        assert all(entry["committed"] for entry in trace)
        assert all(alert.reading_id in {row.id for row in readings} for alert in alerts)
        assert classifications == (messages * 3 if scenario == "WITH_QOS" else 0)
        assert qos_rows == classifications
    by_class = defaultdict(list)
    for item in trace:
        by_class[item["evaluation_class"]].append(item["queue_wait_ms"])
    result = {
        "scenario": scenario, "messages": messages, "repetition": repetition,
        "readings": len(readings), "classifications": classifications,
        "qos_rows": qos_rows, "alerts": len(alerts), "metrics": dict(metrics),
        "ingest_classify_admit_ms": ingest_ms,
        "queue_wait_ms_by_evaluation_class": {
            key: {"count": len(values), "mean_ms": sum(values) / len(values)}
            for key, values in sorted(by_class.items())
        },
        "dispatch": coordinator.snapshot(), "selection_trace": trace,
    }
    engine.dispose()
    return result


def main():
    safe_temp = Path(tempfile.gettempdir()) / "opencode"
    safe_temp.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="qos-corpus-", dir=safe_temp) as directory:
        root = Path(directory)
        # One warm-up is excluded from the reported repetitions.
        run_case(root, "WITH_QOS", 1, 0)
        cases = [run_case(root, scenario, count, repetition)
                 for count in (1, 7)
                 for repetition in (1, 2)
                 for scenario in ("WITH_QOS", "WITHOUT_QOS")]
    print(json.dumps({
        "kind": "isolated_sqlite_preloaded_integration",
        "corpus": {"temperature": 9.5, "humidity": 82.0, "energy": "on"},
        "policy": {"high": 4, "medium": 2, "low": 1},
        "flow_weights": "default 1", "cost_readings": 1,
        "warmup_cases": 1, "repetitions": 2,
        "limitations": ["No MQTT, PostgreSQL or notification channels.",
                        "Preloaded finite input is not a sustained real-time workload.",
                        "Wall-clock observations depend on host and do not establish causality."],
        "cases": cases,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
