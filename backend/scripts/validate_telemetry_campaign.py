"""Opt-in, isolated PostgreSQL + MQTT/TLS campaign for trace reconciliation.

Run with --execute. Only containers created by this invocation are stopped.
Never reads .env, reuses project DB/broker ports, or sends notifications.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
TOPIC = "coldchain/device/CAMPAIGN-001/telemetry"
MIXED = [
    {"temperature": 3.0, "humidity": 87.0, "energy": "on"},
    {"temperature": 6.0, "humidity": 82.0, "energy": "on"},
    {"temperature": 9.5, "humidity": 75.0, "energy": "off"},
    {"temperature": -6.0, "humidity": 97.0, "energy": "on"},
]


def now():
    return datetime.now(timezone.utc)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False),
                    encoding="utf-8")


def read_events(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def docker(*args):
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=90)
    if result.returncode:
        # Do not print argv/environment: generated test passwords can be there.
        raise RuntimeError(f"Docker {args[0]} failed (exit {result.returncode})")
    return result.stdout.strip()


def wait_port(port):
    until = time.monotonic() + 40
    while time.monotonic() < until:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("Isolated service did not open its port")


def producer(manifest_path):
    """Separate OS process using the actual simulator publisher and callbacks."""
    from simulator.devices import ColdRoom
    from simulator.mqtt.client import MQTTClient
    from simulator.mqtt.publisher import DevicePublisher
    from simulator.sensors import EnergyStatusSensor, HumiditySensor, TemperatureSensor

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    client = MQTTClient(
        "127.0.0.1", int(os.environ["CAMPAIGN_MQTT_PORT"]),
        username="campaign", password=os.environ["CAMPAIGN_MQTT_PASSWORD"],
        tls_ca_cert=str(ROOT / "docker/mqtt/certs/ca.crt"),
    )
    last_payload = []
    original_publish = client.publish

    def capture_publish(topic, payload, qos=0):
        last_payload[:] = [payload]
        return original_publish(topic, payload, qos)

    client.publish = capture_publish
    device = ColdRoom(id="campaign", code="CAMPAIGN-001", name="Campaign", location="isolated")
    sensors = {
        "temperature": TemperatureSensor(device=device),
        "humidity": HumiditySensor(device=device),
        "energy": EnergyStatusSensor(device=device),
    }
    for sensor in sensors.values():
        device.add_sensor(sensor)
    publisher = DevicePublisher(client, qos=1)
    client.start()
    try:
        until = time.monotonic() + 15
        while not client.is_connected and time.monotonic() < until:
            time.sleep(0.01)
        if not client.is_connected:
            raise RuntimeError("Publisher connection was not acknowledged")
        start = now()
        schedule = time.monotonic()
        for index, values in enumerate(manifest["corpus"]):
            delay = schedule + index * manifest["period_s"] - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            generated = now()
            measurements = {
                sensors[name]: SimpleNamespace(value=value, timestamp=generated)
                for name, value in values.items()
            }
            if not publisher.publish_telemetry(device, measurements):
                raise RuntimeError("Publication was not accepted")
            if manifest.get("duplicate"):
                if not client.publish(TOPIC, last_payload[0], qos=1):
                    raise RuntimeError("Duplicate publication was not accepted")
        end = now()
        until = time.monotonic() + 20
        while time.monotonic() < until:
            with client._publication_lock:
                if not client._pending_publications:
                    break
            time.sleep(0.01)
        with client._publication_lock:
            if client._pending_publications:
                raise RuntimeError("Publication completion timeout")
        save(manifest_path.with_suffix(".result.json"), {
            "started_at": start.isoformat(), "ended_at": end.isoformat(),
            "qos": 1, "unique_messages": len(manifest["corpus"]),
        })
    finally:
        client.stop()


def run_cases(output, database_url, mqtt_port, mqtt_password):
    import paho.mqtt.client as mqtt
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    import app.acquisition.pipeline as pipeline
    import app.database.infrastructure.session as session_module
    from app.acquisition.infrastructure.mqtt_subscriber import MQTTSubscriber
    from app.acquisition.message_queue import MessageQueue
    from app.acquisition.telemetry_trace import record_trace
    from app.config import BackendConfig
    from app.database.application.persistence_service import PersistenceService
    from app.database.infrastructure.models import (
        AlertORM, DeviceORM, DeviceSensorORM, ExperimentRunORM, SensorReadingORM,
        TrafficClassificationORM, UserORM,
    )
    from app.events.application.event_processing_service import EventProcessingService
    from app.events.domain import ThresholdConfig
    from app.experiments import active
    from app.qos.application.telemetry_evidence import reconcile

    engine = create_engine(database_url)
    factory = sessionmaker(bind=engine, autoflush=False)
    session_module.SessionLocal = factory
    device_id, user_id = uuid4(), uuid4()
    with factory.begin() as db:
        db.add(DeviceORM(id=device_id, code="CAMPAIGN-001", name="Campaign",
                         location="isolated", device_type="cold_room", status="active"))
        db.add(UserORM(id=user_id, name="system", email="campaign@coldchain.invalid",
                       password_hash="!", role="system", is_active=True))
        db.flush()
        db.add_all(DeviceSensorORM(device_id=device_id, sensor_type=sensor)
                   for sensor in ("temperature", "humidity", "energy"))
    config = BackendConfig()
    original_attention = pipeline._attention_loop
    original_process = pipeline._process_work_item
    attention_gate = threading.Event()
    selection = []

    def gated_attention(*args):
        if not attention_gate.wait(90):
            raise RuntimeError("Preload gate timed out")
        original_attention(*args)

    def traced_process(item, state):
        selection.append({
            "work_id": str(item.id), "source_message_id": str(item.source_message_id),
            "sequence": item.sequence, "sensor": item.sensor_name,
            "priority": item.priority,
            "criticality": item.classification.criticality if item.classification else None,
            "selected_at": now().isoformat(),
        })
        return original_process(item, state)

    pipeline._attention_loop = gated_attention
    pipeline._process_work_item = traced_process
    cases = []
    for scenario in ("WITH_QOS", "WITHOUT_QOS"):
        cases.append(("warmup", 0, scenario, MIXED, 0.02, 3, False, False, False))
    for repetition in range(1, 4):
        scenarios = ("WITH_QOS", "WITHOUT_QOS") if repetition % 2 else ("WITHOUT_QOS", "WITH_QOS")
        for label, count, period in (("paced_10_messages_s", 60, 0.1), ("burst", 120, 0)):
            for scenario in scenarios:
                corpus = [MIXED[i % len(MIXED)] for i in range(count)]
                cases.append((label, repetition, scenario, corpus, period, 15, False, False, False))
    band_corpus = [{"humidity": 75.0} if i % 2 == 0 else {"temperature": 9.5}
                   for i in range(200)]
    for scenario in ("WITH_QOS", "WITHOUT_QOS"):
        cases.append(("preloaded_H8_H9", 1, scenario, band_corpus, 0, 15, True, False, False))
    cases += [
        ("controlled_no_subscription", 1, "WITH_QOS", MIXED * 2, 0, 3, False, False, True),
        ("duplicate_delivery", 1, "WITH_QOS", MIXED * 2, 0.02, 5, False, True, False),
        ("producer_process_restart", 1, "WITH_QOS", MIXED * 4, 0.02, 5, False, False, False),
    ]
    results = []
    try:
        for number, (label, repetition, scenario, corpus, period, grace, preload, duplicate, no_sub) in enumerate(cases):
            run_id = uuid4()
            directory = output / f"{number:02d}-{label}-{scenario}-{repetition}"
            directory.mkdir()
            backend_path = directory / "backend.jsonl"
            os.environ["TELEMETRY_TRACE_FILE"] = str(backend_path)
            with factory.begin() as db:
                db.add(ExperimentRunORM(
                    id=run_id, scenario=scenario, started_at=now(),
                    config_snapshot=json.dumps(config.effective_qos_config()),
                ))
            active.set_active_run(run_id, scenario)
            attention_gate.clear()
            if not preload:
                attention_gate.set()
            selection.clear()
            queue = MessageQueue(1000)
            state = SimpleNamespace(
                classifications=[], events=[], alerts=[], notifications=[], enriched_events=[],
                backend_config=config, persistence_service=PersistenceService(),
                notification_service=None,
                event_processing_service=EventProcessingService(
                    ThresholdConfig(min_temperature=0, max_temperature=4,
                                    min_humidity=85, max_humidity=90,
                                    allowed_energy_states=frozenset({"on"})),
                    device_mapping={"CAMPAIGN-001": device_id}, user_id=user_id,
                ),
            )
            coordinator = pipeline.build_dispatch_coordinator(state)
            worker = pipeline.AcquisitionPipeline(queue, state, shutdown_timeout=120)
            subscriber = MQTTSubscriber(queue)
            ready = threading.Event()
            receiver = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            receiver.username_pw_set("campaign", mqtt_password)
            receiver.tls_set(ca_certs=str(ROOT / "docker/mqtt/certs/ca.crt"))
            receiver.on_connect = lambda c, u, f, r, p: (
                ready.set() if no_sub else c.subscribe(TOPIC, qos=1)
            ) if not r.is_failure else None
            receiver.on_subscribe = lambda c, u, mid, reasons, p: (
                ready.set() if all(not r.is_failure for r in reasons) else None
            )
            receiver.on_message = subscriber.on_message
            receiver.connect("127.0.0.1", mqtt_port)
            receiver.loop_start()
            worker.start()
            try:
                if not ready.wait(15):
                    raise RuntimeError("Receiver connection/subscription timeout")
                chunks = [corpus]
                if label == "producer_process_restart":
                    chunks = [corpus[:len(corpus) // 2], corpus[len(corpus) // 2:]]
                sender_paths, sender_results = [], []
                for part, values in enumerate(chunks):
                    manifest_path = directory / f"producer-{part}.manifest.json"
                    save(manifest_path, {"corpus": values, "period_s": period, "duplicate": duplicate})
                    sender_path = directory / f"producer-{part}.jsonl"
                    env = dict(os.environ)
                    env.update({
                        "COLDCHAIN_RUN_ID": str(run_id),
                        "TELEMETRY_TRACE_FILE": str(sender_path),
                        "CAMPAIGN_MQTT_PORT": str(mqtt_port),
                        "CAMPAIGN_MQTT_PASSWORD": mqtt_password,
                    })
                    child = subprocess.run(
                        [sys.executable, "-B", str(Path(__file__).resolve()), "--producer", str(manifest_path)],
                        env=env, capture_output=True, text=True, timeout=120,
                    )
                    if child.returncode:
                        # Logs contain no credential-bearing commands or connection URLs.
                        (directory / f"producer-{part}.log").write_text(child.stderr, encoding="utf-8")
                        raise RuntimeError(f"Producer failed; see {directory.name}/producer-{part}.log")
                    sender_paths.append(sender_path)
                    sender_results.append(json.loads(manifest_path.with_suffix(".result.json").read_text()))
                start = min(datetime.fromisoformat(row["started_at"]) for row in sender_results)
                end = max(datetime.fromisoformat(row["ended_at"]) for row in sender_results)
                # Observe a fixed, predeclared grace window, not 'wait until
                # all received', which would hide loss by construction.
                if preload:
                    until = time.monotonic() + 60
                    while time.monotonic() < until:
                        events = read_events(backend_path)
                        if sum(row["event"] == "received" for row in events) >= len(corpus):
                            break
                        time.sleep(0.05)
                    if not queue.wait_run_ingested(run_id, 60):
                        raise RuntimeError("Backlog did not finish ingestion")
                    snapshot = coordinator.snapshot()
                    save(directory / "preload.json", snapshot)
                    if snapshot["pending"] != len(corpus):
                        raise RuntimeError("Preloaded backlog did not contain every sensor reading")
                    attention_gate.set()
                delay = (end + timedelta(seconds=grace) - now()).total_seconds()
                if delay > 0:
                    time.sleep(delay)
                observed = now()
                if not queue.wait_run_ingested(run_id, 120) or not coordinator.wait_until_idle(120):
                    raise RuntimeError("Pipeline did not drain")
                record_trace("observation_closed", run_id=str(run_id))
                producer_rows = [row for path in sender_paths for row in read_events(path)]
                backend_rows = read_events(backend_path)
                report = reconcile(
                    producer_rows, backend_rows, started_at=start, emission_ended_at=end,
                    observed_until=observed, grace_seconds=grace, run_id=str(run_id),
                    complete_capture=True,
                )
                expected_received = 0 if no_sub else len(corpus)
                if report["status"] != "final" or report["counts"]["sent_unique"] != len(corpus):
                    raise RuntimeError("Campaign evidence is incomplete")
                if report["counts"]["received_unique"] != expected_received:
                    raise RuntimeError("Unexpected message loss; evidence preserved")
                if report["counts"]["duplicate_receptions"] != (len(corpus) if duplicate else 0):
                    raise RuntimeError("Duplicate reconciliation mismatch")
                with factory() as db:
                    readings = db.query(SensorReadingORM).filter_by(run_id=run_id).all()
                    ids = {row.id for row in readings}
                    classifications = db.query(TrafficClassificationORM).filter(
                        TrafficClassificationORM.reading_id.in_(ids)).all()
                    alerts = db.query(AlertORM).filter_by(run_id=run_id).all()
                    expected_readings = 0 if no_sub else sum(len(values) for values in corpus)
                    if len(readings) != expected_readings or any(alert.reading_id not in ids for alert in alerts):
                        raise RuntimeError("PostgreSQL integrity mismatch")
                    if len(classifications) != (len(readings) if scenario == "WITH_QOS" else 0):
                        raise RuntimeError("Classification scenario mismatch")
                    tc_by_reading = {row.reading_id: row for row in classifications}
                    save(directory / "database-readings.json", [
                        {"work_id": str(row.id), "source_message_id": str(row.source_message_id),
                         "sensor": row.sensor_name, "timestamp": row.timestamp.isoformat(),
                         "criticality": tc_by_reading[row.id].criticality if row.id in tc_by_reading else None}
                        for row in readings
                    ])
                if report["counts"]["persisted_readings"] != expected_readings:
                    raise RuntimeError("Persistence exceeded the declared window; inspect the traces")
                if scenario == "WITHOUT_QOS":
                    sequences = [row["sequence"] for row in selection]
                    if sequences != sorted(sequences):
                        raise RuntimeError("WITHOUT_QOS did not preserve FIFO")
                if preload and scenario == "WITH_QOS":
                    # Both bands have 100 admitted jobs at release. First 100
                    # selections must give H8:H9 = 40:60 for unit cost.
                    prefix = Counter(row["criticality"] for row in selection[:100])
                    if prefix != {8: 40, 9: 60}:
                        raise RuntimeError(f"Unexpected real-backlog WFQ share: {prefix}")
                save(directory / "selection.json", selection)
                save(directory / "reconciliation.json", report)
                result = {
                    "label": label, "repetition": repetition, "scenario": scenario,
                    "run_id": str(run_id), "directory": directory.name,
                    "corpus_messages": len(corpus), "period_s": period,
                    "preloaded_attention": preload, "grace_seconds": grace,
                    "database_readings": len(readings), "database_alerts": len(alerts),
                    "classifications": len(classifications), "reconciliation": report,
                    "selection_prefix_100_by_criticality": dict(Counter(
                        str(row["criticality"]) for row in selection[:100])),
                }
                if label != "warmup":
                    results.append(result)
                save(output / "results.partial.json", results)
                print(f"{number + 1}/{len(cases)} {label} {scenario}: "
                      f"{report['counts']['sent_unique']} sent, {report['counts']['received_unique']} received, "
                      f"{len(readings)} readings, PDR {report['pdr_percent']}%", flush=True)
            finally:
                attention_gate.set()
                receiver.disconnect()
                receiver.loop_stop()
                worker.stop()
                active.clear_active_run()
                with factory.begin() as db:
                    db.get(ExperimentRunORM, run_id).finished_at = now()
        with engine.connect() as db:
            revision = db.execute(text("select version_num from alembic_version")).scalar_one()
        return {
            "kind": "real_isolated_postgres_mqtt_tls_trace_campaign",
            "cases": results, "warmup_cases_excluded": 2, "repetitions": 3,
            "migration_revision": revision, "notifications": "disabled",
            "config": config.effective_qos_config(),
            "limitations": [
                "Synthetic telemetry, real MQTT/TLS transport and PostgreSQL commits.",
                "Same Windows host clock for producer/backend; not a clock-sync validation.",
                "Matrix accepts C=3,6,8,9; H7 is not reachable through current valid telemetry.",
                "Preloaded backlog cases are functional scheduling checks, not real-time latency benchmarks.",
                "Controlled no-subscription loss is intentional application loss, not IP packet loss.",
                "Local repetitions do not establish universal QoS improvement or network reliability.",
            ],
        }
    finally:
        attention_gate.set()
        pipeline._attention_loop = original_attention
        pipeline._process_work_item = original_process
        active.clear_active_run()
        engine.dispose()


def campaign(output):
    """Create disposable containers with no access to the project's SQL volume."""
    suffix = uuid4().hex[:10]
    output.mkdir(parents=True, exist_ok=False)
    config_dir = output / "broker"
    config_dir.mkdir()
    certificates = ROOT / "docker/mqtt/certs"
    for name in ("ca.crt", "server.crt", "server.key"):
        if not (certificates / name).is_file():
            raise RuntimeError(f"Missing local TLS prerequisite: {name}")
    password = secrets.token_urlsafe(24)
    db_password = secrets.token_urlsafe(24)
    db_name = f"b4_isolated_trace_{suffix}"
    owned = []
    try:
        docker("run", "--rm", "--mount", f"type=bind,source={config_dir},target=/campaign",
               "eclipse-mosquitto:2", "mosquitto_passwd", "-b", "-c",
               "/campaign/passwd", "campaign", password)
        docker("run", "--rm", "--mount", f"type=bind,source={config_dir},target=/campaign",
               "eclipse-mosquitto:2", "chmod", "644", "/campaign/passwd")
        (config_dir / "mosquitto.conf").write_text(
            "listener 8883\nprotocol mqtt\nallow_anonymous false\n"
            "password_file /campaign/passwd\ncertfile /certs/server.crt\n"
            "keyfile /certs/server.key\ntls_version tlsv1.2\n"
            "persistence false\nlog_dest stdout\n", encoding="utf-8")
        postgres_name, mqtt_name = f"coldchain-trace-pg-{suffix}", f"coldchain-trace-mqtt-{suffix}"
        docker("run", "-d", "--name", postgres_name,
               "--label", f"coldchain.trace.campaign={suffix}", "-p", "127.0.0.1::5432",
               "--tmpfs", "/var/lib/postgresql/data:rw",
               "-e", f"POSTGRES_DB={db_name}", "-e", "POSTGRES_USER=campaign",
               "-e", f"POSTGRES_PASSWORD={db_password}", "postgres:16-alpine")
        owned.append(postgres_name)
        docker("run", "-d", "--name", mqtt_name,
               "--label", f"coldchain.trace.campaign={suffix}", "-p", "127.0.0.1::8883",
               "--mount", f"type=bind,source={config_dir},target=/campaign,readonly",
               "--mount", f"type=bind,source={certificates},target=/certs,readonly",
               "eclipse-mosquitto:2", "mosquitto", "-c", "/campaign/mosquitto.conf")
        owned.append(mqtt_name)
        pg_port = int(docker("port", postgres_name, "5432/tcp").rsplit(":", 1)[1])
        mqtt_port = int(docker("port", mqtt_name, "8883/tcp").rsplit(":", 1)[1])
        wait_port(pg_port)
        wait_port(mqtt_port)
        until = time.monotonic() + 40
        while time.monotonic() < until:
            probe = subprocess.run(["docker", "exec", postgres_name, "pg_isready",
                                    "-U", "campaign", "-d", db_name], capture_output=True)
            if probe.returncode == 0:
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("PostgreSQL readiness timeout")
        url = f"postgresql+psycopg://campaign:{db_password}@127.0.0.1:{pg_port}/{db_name}"
        os.environ.update({
            "DATABASE_URL": url, "COLDCHAIN_SIM_WORKER_ENABLED": "false",
            "SMTP_ENABLED": "false", "PUSH_ENABLED": "false",
            "JWT_SECRET_KEY": secrets.token_urlsafe(32),
            "TELEMETRY_CLOCK_DOMAIN": f"same-host-{suffix}",
        })
        for key in ("QOS_WFQ_FLOW_WEIGHTS", "QOS_WFQ_BAND_WEIGHTS",
                    "QOS_HIGH_QUOTA", "QOS_MEDIUM_QUOTA", "QOS_LOW_QUOTA"):
            os.environ.pop(key, None)
        with (output / "migration.log").open("w", encoding="utf-8") as log:
            migration = subprocess.run(
                [sys.executable, "-B", "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
                cwd=ROOT / "backend", stdout=log, stderr=log, timeout=120,
            )
        if migration.returncode:
            raise RuntimeError("Isolated migration failed; inspect migration.log")
        report = run_cases(output, url, mqtt_port, password)
        report["infrastructure"] = {
            "postgres_image": "postgres:16-alpine", "postgres_port": pg_port,
            "mqtt_image": "eclipse-mosquitto:2", "mqtt_port": mqtt_port,
            "loopback_only": True, "postgres_ephemeral_tmpfs": True,
            "tls_verification": "required", "containers": owned.copy(),
        }
        save(output / "campaign.json", report)
        print(f"Campaign completed: {output / 'campaign.json'}", flush=True)
    finally:
        cleanup = []
        for name in reversed(owned):
            logs = subprocess.run(["docker", "logs", name], capture_output=True, text=True, timeout=15)
            (output / f"{name}.log").write_text(logs.stdout + logs.stderr, encoding="utf-8")
            result = subprocess.run(["docker", "stop", name], capture_output=True, text=True, timeout=45)
            removed = subprocess.run(["docker", "rm", name], capture_output=True, text=True, timeout=15)
            cleanup.append({"container": name, "stopped": result.returncode == 0,
                            "removed": removed.returncode == 0})
        save(output / "cleanup.json", cleanup)
        # Only ephemeral generated hashes, never project credentials, remain.
        # Certificates were mounted read-only and were not copied.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--producer", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    logging.basicConfig(level=logging.ERROR)
    if args.producer:
        producer(args.producer)
    elif args.execute and args.output:
        campaign(args.output.resolve())
    else:
        parser.error("Explicit --execute and a new --output directory are required")


if __name__ == "__main__":
    main()
