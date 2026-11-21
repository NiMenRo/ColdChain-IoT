"""Explicit opt-in load campaign against isolated PG and MQTT/TLS.

Requires B4_DATABASE_URL, B4_MQTT_PORT, B4_MQTT_CA, B4_MQTT_USER and
B4_MQTT_PASSWORD. Refuses normal project ports and non-isolated DB names.
Creates test rows; run only against a disposable database and broker.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.engine import make_url

url = make_url(os.environ["B4_DATABASE_URL"])
port = int(os.environ["B4_MQTT_PORT"])
if (url.drivername != "postgresql+psycopg" or url.host != "127.0.0.1"
        or not url.port or url.port == 5433
        or not (url.database or "").startswith("b4_isolated_")
        or port in (1883, 8883) or not 1 <= port <= 65535):
    raise SystemExit("Refusing non-isolated database or broker")
os.environ["DATABASE_URL"] = os.environ["B4_DATABASE_URL"]
os.environ["COLDCHAIN_SIM_WORKER_ENABLED"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import paho.mqtt.client as mqtt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database.infrastructure.session as session_module
from app.acquisition.infrastructure.mqtt_subscriber import MQTTSubscriber
from app.acquisition.message_queue import MessageQueue
from app.acquisition.pipeline import AcquisitionPipeline, build_dispatch_coordinator
from app.database.application.persistence_service import PersistenceService
from app.database.infrastructure.models import (
    AlertORM, DeviceORM, DeviceSensorORM, ExperimentMetricORM, ExperimentRunORM,
    QoSMetricORM, SensorReadingORM, TrafficClassificationORM, UserORM,
)
from app.events.application.event_processing_service import EventProcessingService
from app.events.domain import ThresholdConfig
from app.experiments import active
import app.acquisition.pipeline as acquisition

logging.getLogger("app.acquisition.pipeline").setLevel(logging.ERROR)
LOADS = (("low_2_messages_s", 30, 0.5), ("high_20_messages_s", 300, 0.05))
REPETITIONS = 3


def main():
    engine = create_engine(url)
    factory = sessionmaker(bind=engine, autoflush=False)
    session_module.SessionLocal = factory
    device_id, user_id = uuid4(), uuid4()
    with factory.begin() as db:
        db.add(DeviceORM(id=device_id, code="CAVA-B4", name="B4", location="isolated",
                         device_type="cold_room", status="active"))
        db.add(UserORM(id=user_id, name="system", email="b4@coldchain.invalid",
                       password_hash="!", role="system", is_active=True))
        db.flush()
        db.add_all(DeviceSensorORM(device_id=device_id, sensor_type=s)
                   for s in ("temperature", "humidity", "energy"))
    queue = MessageQueue(1000)
    thresholds = ThresholdConfig(min_temperature=0, max_temperature=4,
                                 min_humidity=85, max_humidity=90,
                                 allowed_energy_states=frozenset({"on"}))
    state = SimpleNamespace(
        classifications=[], events=[], alerts=[], enriched_events=[], notifications=[],
        persistence_service=PersistenceService(), notification_service=None,
        event_processing_service=EventProcessingService(
            thresholds, device_mapping={"CAVA-B4": device_id}, user_id=user_id),
    )
    coordinator = build_dispatch_coordinator(state)
    worker = AcquisitionPipeline(queue, state)
    trace = []
    classification_times = defaultdict(list)
    current_run = [None]
    _, classifier, evaluator = acquisition._ingestion_services()
    original_evaluate, original_classify = evaluator.evaluate, classifier.classify

    def timed_call(stage, func, *args, **kwargs):
        wall_start = time.perf_counter_ns()
        cpu_start = time.thread_time_ns()
        try:
            return func(*args, **kwargs)
        finally:
            if current_run[0] is not None:
                classification_times[current_run[0]].append({
                    "stage": stage,
                    "wall_ns": time.perf_counter_ns() - wall_start,
                    "thread_cpu_ns": time.thread_time_ns() - cpu_start,
                })

    evaluator.evaluate = lambda *args, **kwargs: timed_call(
        "risk_evaluation", original_evaluate, *args, **kwargs)
    classifier.classify = lambda *args, **kwargs: timed_call(
        "classification", original_classify, *args, **kwargs)
    original_process = acquisition._process_work_item

    def traced_process(item, app_state):
        selected = time.monotonic()
        entry = {
            "run_id": str(item.run_id) if item.run_id else None,
            "sequence": item.sequence, "sensor": item.sensor_name,
            "work_id": str(item.id),
            "evaluation_class": {"temperature": "high", "humidity": "medium", "energy": "low"}[item.sensor_name],
            "dispatch_priority": item.priority,
            "queue_wait_ms": max(0.0, (selected - item.admitted_monotonic) * 1000),
        }
        trace.append(entry)
        try:
            result = original_process(item, app_state)
            entry["committed"] = result is not None
            return result
        finally:
            entry["attention_ms"] = (time.monotonic() - selected) * 1000

    acquisition._process_work_item = traced_process
    subscriber = MQTTSubscriber(queue)
    ready = threading.Event()
    reception = threading.Condition()
    received_count = 0
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(os.environ["B4_MQTT_USER"], os.environ["B4_MQTT_PASSWORD"])
    client.tls_set(ca_certs=os.environ["B4_MQTT_CA"])
    topic = "coldchain/device/CAVA-B4/telemetry"
    client.on_connect = lambda c, u, f, reason, p: c.subscribe(topic, qos=1) if not reason.is_failure else None
    client.on_subscribe = lambda c, u, mid, reasons, p: ready.set() if all(not r.is_failure for r in reasons) else None

    def on_message(c, userdata, message):
        nonlocal received_count
        subscriber.on_message(c, userdata, message)
        with reception:
            received_count += 1
            reception.notify_all()

    client.on_message = on_message
    client.connect("127.0.0.1", port)
    client.loop_start()
    worker.start()
    results = []
    try:
        if not ready.wait(10):
            raise RuntimeError("MQTT subscription was not acknowledged")
        cases = [(True, "warmup", 1, 0.1, 0, scenario)
                 for scenario in ("WITH_QOS", "WITHOUT_QOS")]
        cases += [(False, level, count, period, repetition, scenario)
                  for level, count, period in LOADS
                  for repetition in range(1, REPETITIONS + 1)
                  for scenario in ("WITH_QOS", "WITHOUT_QOS")]
        for warmup, level, message_count, period, repetition, scenario in cases:
            run_id = uuid4()
            with factory.begin() as db:
                db.add(ExperimentRunORM(id=run_id, scenario=scenario,
                                        started_at=datetime.now(timezone.utc)))
            active.set_active_run(run_id, scenario)
            current_run[0] = str(run_id)
            initial_transport_rejected = queue.rejected
            initial_dispatch = coordinator.counters
            with reception:
                initial_received = received_count
            sent_at = []
            publications = []
            window_start = time.monotonic()
            for message_index in range(message_count):
                scheduled = window_start + message_index * period
                remaining = scheduled - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
                payload = {"device_code": "CAVA-B4", "device_type": "cold_room",
                           "temperature": 9.5, "humidity": 82.0, "energy": "on",
                           "timestamp": datetime.now(timezone.utc).isoformat()}
                info = client.publish(topic, json.dumps(payload), qos=1)
                assert info.rc == mqtt.MQTT_ERR_SUCCESS
                publications.append(info)
                sent_at.append(time.monotonic())
            # Do not throttle arrivals by waiting for each receipt/commit.
            # Acknowledge all publications and receipts before testing drain.
            for info in publications:
                info.wait_for_publish(timeout=10)
                if not info.is_published():
                    raise RuntimeError("MQTT publish timed out")
            with reception:
                if not reception.wait_for(
                        lambda: received_count >= initial_received + message_count, timeout=30):
                    raise RuntimeError("MQTT receipt timed out")
                assert received_count - initial_received == message_count
            if not queue.wait_run_ingested(run_id, 120) or not coordinator.wait_until_idle(120):
                raise RuntimeError("Pipeline did not drain")
            elapsed = time.monotonic() - window_start
            current_run[0] = None
            with factory() as db:
                rows = db.query(SensorReadingORM).filter_by(run_id=run_id).all()
                ids = {row.id for row in rows}
                classifications = db.query(TrafficClassificationORM).filter(
                    TrafficClassificationORM.reading_id.in_(ids)).all()
                tc_ids = {row.id for row in classifications}
                qos = db.query(QoSMetricORM).filter(QoSMetricORM.classification_id.in_(tc_ids)).all()
                alerts = db.query(AlertORM).filter_by(run_id=run_id).all()
                metrics = db.query(ExperimentMetricORM).filter_by(run_id=run_id).all()
                assert len(rows) == message_count * 3 and len({r.source_message_id for r in rows}) == message_count
                assert {r.sensor_name for r in rows} == {"temperature", "humidity", "energy"}
                assert len(alerts) == message_count * 2
                for row in rows:
                    assert row.processing_version == 2
                    assert (row.temperature, row.humidity, row.energy) == {
                        "temperature": (9.5, None, None),
                        "humidity": (None, 82.0, None),
                        "energy": (None, None, "on"),
                    }[row.sensor_name]
                assert all(sum(r.source_message_id == source for r in rows) == 3
                           for source in {r.source_message_id for r in rows})
                assert all(a.reading_id in ids for a in alerts)
                assert len(classifications) == (message_count * 3 if scenario == "WITH_QOS" else 0)
                assert len(qos) == len(classifications)
                assert all(q.packet_loss is None and q.pdr is None and q.throughput is None for q in qos)
                run_trace = [entry for entry in trace if entry["run_id"] == str(run_id)]
                assert len(run_trace) == message_count * 3 and all(entry["committed"] for entry in run_trace)
                assert {entry["work_id"] for entry in run_trace} == {str(row.id) for row in rows}
                if scenario == "WITHOUT_QOS":
                    assert [entry["sequence"] for entry in run_trace] == sorted(entry["sequence"] for entry in run_trace)
                by_class = defaultdict(list)
                for entry in run_trace:
                    by_class[entry["evaluation_class"]].append(entry["queue_wait_ms"])
                stage_times = classification_times[str(run_id)]
                assert len(stage_times) == (message_count * 6 if scenario == "WITH_QOS" else 0)
                assert queue.rejected == initial_transport_rejected
                assert coordinator.counters["rejected"] == initial_dispatch["rejected"]
                assert coordinator.counters["failed"] == initial_dispatch["failed"]
                final_dispatch = coordinator.counters
                assert final_dispatch["pending"] == final_dispatch["in_flight"] == 0
                assert final_dispatch["completed"] - initial_dispatch["completed"] == len(rows)
                costs = None
                if stage_times:
                    costs = {}
                    for stage in ("risk_evaluation", "classification"):
                        samples = [x for x in stage_times if x["stage"] == stage]
                        costs[stage] = {
                            "count": len(samples),
                            "wall_ms_total": sum(x["wall_ns"] for x in samples) / 1e6,
                            # On Windows the thread CPU clock can quantize
                            # every short call to zero; this is unmeasurable,
                            # not evidence that no CPU time was consumed.
                            "thread_cpu_ms_total": (
                                sum(x["thread_cpu_ns"] for x in samples) / 1e6
                                if any(x["thread_cpu_ns"] for x in samples) else None
                            ),
                        }
                result = {
                    "scenario": scenario, "level": level, "repetition": repetition,
                    "messages": message_count, "readings": len(rows),
                    "classifications": len(classifications), "qos_rows": len(qos),
                    "alerts": len(alerts), "metric_types": sorted({m.metric_type for m in metrics}),
                    "classification_cost": costs,
                    "publication_target_interval_s": period,
                    "publication_actual_duration_s": sent_at[-1] - sent_at[0] if len(sent_at) > 1 else None,
                    "publication_actual_messages_s": (
                        (message_count - 1) / (sent_at[-1] - sent_at[0])
                        if len(sent_at) > 1 else None
                    ),
                    "pending_after_drain": final_dispatch["pending"],
                    "in_flight_after_drain": final_dispatch["in_flight"],
                    "completed": final_dispatch["completed"] - initial_dispatch["completed"],
                    "window_until_drained_s": elapsed,
                    "messages_per_second_window": message_count / elapsed,
                    "readings_persisted_per_second_window": len(rows) / elapsed,
                    "transport_rejected": queue.rejected - initial_transport_rejected,
                    "dispatch_rejected": coordinator.counters["rejected"] - initial_dispatch["rejected"],
                    "dispatch_failed": coordinator.counters["failed"] - initial_dispatch["failed"],
                    "queue_wait_ms_by_evaluation_class": {
                        key: {"count": len(values), "mean_ms": sum(values) / len(values)}
                        for key, values in sorted(by_class.items())
                    },
                    "selection_trace": run_trace,
                }
                if not warmup:
                    results.append(result)
            active.clear_active_run()
    finally:
        active.clear_active_run()
        client.disconnect()
        client.loop_stop()
        worker.stop()
        acquisition._process_work_item = original_process
        evaluator.evaluate = original_evaluate
        classifier.classify = original_classify
        engine.dispose()
    print(json.dumps({"kind": "isolated_postgres_mqtt_tls_campaign",
                      "notification_channels": "disabled",
                      "warmup_cases": 2, "repetitions": REPETITIONS,
                      "policy": {"high": 4, "medium": 2, "low": 1},
                      "flow_weights": "default 1", "cost_per_reading": 1,
                      "clock_resolution_s": {
                          "elapsed": time.get_clock_info("perf_counter").resolution,
                          "thread_cpu": time.get_clock_info("thread_time").resolution,
                      },
                      "limitations": ["Finite paced load; not an infinite saturation guarantee.",
                                      "Classification instrumentation adds overhead.",
                                      "Thread CPU and elapsed time are distinct; zero-resolution CPU samples are unavailable.",
                                      "No causality inferred from these measurements."],
                      "cases": results}, indent=2))


if __name__ == "__main__":
    main()
