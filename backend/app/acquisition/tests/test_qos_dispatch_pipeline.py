"""B1 — sealed reception, per-reading admission, real selection and attention."""

from __future__ import annotations

import itertools
import threading
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event as sqlalchemy_event
from sqlalchemy.orm import sessionmaker

import app.acquisition.pipeline as pipeline
import app.database.infrastructure.session as session_module
from app.acquisition.infrastructure.mqtt_subscriber import MQTTSubscriber
from app.acquisition.message_queue import MessageQueue
from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification
from app.database.application.persistence_service import PersistenceService
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import (
    AlertORM,
    DeviceORM,
    DeviceSensorORM,
    ExperimentMetricORM,
    ExperimentRunORM,
    NotificationORM,
    QoSMetricORM,
    SensorReadingORM,
    TrafficClassificationORM,
    UserORM,
)
from app.events.application.event_processing_service import EventProcessingService
from app.events.domain import Alert, ThresholdConfig
from app.experiments import active
from app.qos.application.dispatcher import DispatchCoordinator
from app.qos.application.qos_metrics_service import QoSMetricsService
from app.qos.application.traffic_planning_service import TrafficPlanningService
from app.qos.domain.work_item import WorkItem

NOW = datetime(2026, 11, 19, 12, tzinfo=timezone.utc)
THRESHOLDS = dict(
    min_temperature=0.0,
    max_temperature=4.0,
    min_humidity=85.0,
    max_humidity=90.0,
    allowed_energy_states=frozenset({"on"}),
)


@pytest.fixture(autouse=True)
def _clear_active_run():
    active.clear_active_run()
    yield
    active.clear_active_run()


@pytest.fixture()
def db_factory(tmp_path):
    db_file = str(tmp_path / "dispatch.db")
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        future=True,
    )

    @sqlalchemy_event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, connection_record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, future=True)
    yield factory
    engine.dispose()


def _work(sequence, priority="low", scenario="WITH_QOS", sensor="energy", value=1.0, run_id=None):
    queues = {"low": "FIFO", "medium": "Round Robin", "high": "WFQ"}
    criticalities = {"low": 3.0, "medium": 6.0, "high": 9.0}
    work_id = uuid.uuid4()
    classification = None
    if scenario == "WITH_QOS":
        classification = TrafficClassification(
            id=uuid.uuid4(),
            reading_id=work_id,
            criticality=criticalities[priority],
            priority=priority,
            queue=queues[priority],
            classification_time=NOW,
            timestamp=NOW,
        )
    raw_value = "on" if sensor == "energy" else value
    return WorkItem.from_reading(
        NormalizedReading(
            "CAVA-001", "cold_room", sensor, value, NOW.isoformat(), raw_value
        ),
        id=work_id,
        source_message_id=uuid.uuid4(),
        sequence=sequence,
        scenario=scenario,
        run_id=run_id,
        admitted_at=NOW,
        admitted_monotonic=float(sequence),
        classification=classification,
    )


def _message(code="CAVA-001", temperature=3.0, humidity=87.0, energy="on"):
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    return {
        "topic": f"coldchain/device/{code}/telemetry",
        "payload": {
            "device_code": code,
            "device_type": "cold_room",
            "temperature": temperature,
            "humidity": humidity,
            "energy": energy,
            "timestamp": now,
        },
        "device_origin": {"device_code": code, "device_type": "cold_room"},
        "received_at": now,
    }


def _seed_device(factory, code="CAVA-001"):
    with factory() as db:
        with db.begin():
            device = DeviceORM(
                code=code, name="Cava", location="Lab",
                device_type="cold_room", status="active",
            )
            db.add(device)
            db.flush()
            for sensor_type in ("temperature", "humidity", "energy"):
                db.add(DeviceSensorORM(device_id=device.id, sensor_type=sensor_type))
            user = UserORM(
                name="system", email="system@coldchain.local",
                password_hash="!", role="system", is_active=True,
            )
            db.add(user)
            db.flush()
            device_id, user_id = device.id, user.id
    return device_id, user_id


# -- transport ----------------------------------------------------------------


def test_transport_queue_rejects_new_message_without_evicting_pending():
    queue = MessageQueue(2)
    assert queue.append({"n": 1}) is True
    assert queue.append({"n": 2}) is True
    assert queue.append({"n": 3}) is False
    assert [m["n"] for m in queue.get_all()] == [1, 2]
    assert queue.rejected == 1


def test_subscriber_seals_experiment_context_at_reception():
    run_id = uuid.uuid4()
    active.set_active_run(run_id, "WITHOUT_QOS")
    queue = MessageQueue(10)
    subscriber = MQTTSubscriber(queue)

    import json

    payload = _message()["payload"]
    msg = SimpleNamespace(
        payload=json.dumps(payload).encode("utf-8"),
        topic="coldchain/device/CAVA-001/telemetry",
    )
    subscriber.on_message(None, None, msg)
    active.clear_active_run()

    sealed = queue.pop()
    assert sealed["scenario"] == "WITHOUT_QOS"
    assert sealed["run_id"] == str(run_id)
    assert isinstance(sealed["received_monotonic"], float)


def test_subscriber_reports_transport_rejection():
    queue = MessageQueue(1)
    subscriber = MQTTSubscriber(queue)
    import json

    payload = _message()["payload"]
    msg = SimpleNamespace(
        payload=json.dumps(payload).encode("utf-8"),
        topic="coldchain/device/CAVA-001/telemetry",
    )
    subscriber.on_message(None, None, msg)
    subscriber.on_message(None, None, msg)
    assert len(queue) == 1
    assert queue.rejected == 1


def test_transport_rejection_is_recorded_for_sealed_run(monkeypatch, db_factory):
    import json

    run_id = uuid.uuid4()
    _seed_run(db_factory, run_id)
    monkeypatch.setattr(session_module, "SessionLocal", db_factory)
    active.set_active_run(run_id, "WITH_QOS")
    queue = MessageQueue(1)
    subscriber = MQTTSubscriber(queue)
    msg = SimpleNamespace(
        payload=json.dumps(_message()["payload"]).encode("utf-8"),
        topic="coldchain/device/CAVA-001/telemetry",
    )
    subscriber.on_message(None, None, msg)
    subscriber.on_message(None, None, msg)
    with db_factory() as db:
        metric = db.query(ExperimentMetricORM).filter_by(
            run_id=run_id, metric_type="messages_rejected_transport",
        ).one()
        assert metric.value == 1
    assert queue.rejected == 1


# -- admission and selection --------------------------------------------------


def test_coordinator_rejects_new_work_when_capacity_is_full():
    coordinator = DispatchCoordinator(TrafficPlanningService(), capacity=2)
    first, second, third = (_work(i) for i in range(3))

    accepted, rejected = coordinator.admit_many([first, second, third])

    assert accepted == [first, second]
    assert rejected == [third]
    assert coordinator.pending == 2
    assert coordinator.counters["rejected"] == 1
    assert [coordinator.select_next(), coordinator.select_next()] == [first, second]
    assert coordinator.select_next() is None


def test_runtime_samples_pending_identity_and_bounds_recent_failures():
    coordinator = DispatchCoordinator(TrafficPlanningService(), capacity=10, failure_capacity=2)
    items = [_work(i, "high", sensor="temperature", value=9.5) for i in range(3)]
    assert len(coordinator.admit_many(items)[0]) == 3
    snapshot = coordinator.snapshot()
    sample = snapshot["pending_sample"]["high"]
    assert {entry["work_id"] for entry in sample} == {str(item.id) for item in items}
    assert all(entry["device_code"] == "CAVA-001" and entry["sensor_name"] == "temperature" for entry in sample)
    assert coordinator.pending == 3
    for _ in items:
        assert coordinator.select_next() is not None
        coordinator.finish(success=False)
    snapshot = coordinator.snapshot()
    assert snapshot["failed"] == 3
    assert len(snapshot["recent_failures"]) == 2
    assert snapshot["queues"]["high"] == 0
    assert snapshot["pending_sample"]["high"] == []


def test_coordinator_uses_weighted_policy_and_without_qos_fifo():
    coordinator = DispatchCoordinator(TrafficPlanningService(), capacity=20)
    low = _work(0, "low")
    high_one = _work(1, "high")
    medium = _work(2, "medium")
    high_two = _work(3, "high")
    for item in (low, high_one, medium, high_two):
        assert coordinator.admit(item)

    assert [coordinator.select_next() for _ in range(4)] == [
        high_one, high_two, medium, low,
    ]
    assert coordinator.select_next() is None

    without = DispatchCoordinator(TrafficPlanningService(), capacity=10)
    fifo_items = [_work(i, scenario="WITHOUT_QOS") for i in range(3)]
    assert all(without.admit(item) for item in fifo_items)
    assert [without.select_next() for _ in range(3)] == fifo_items
    assert without.snapshot()["queues"] == {"high": 0, "medium": 0, "low": 0}


def test_pending_work_has_no_attention_effect_until_selected(monkeypatch):
    coordinator = DispatchCoordinator(TrafficPlanningService(), capacity=10)
    state = SimpleNamespace()
    stop = threading.Event()
    processed = []
    first_started = threading.Event()
    release_first = threading.Event()

    def fake_process(work_item, app_state):
        processed.append(work_item.id)
        if len(processed) == 1:
            first_started.set()
            assert release_first.wait(5.0)

    monkeypatch.setattr(pipeline, "_process_work_item", fake_process)
    attention = threading.Thread(
        target=pipeline._attention_loop,
        args=(coordinator, state, stop),
        daemon=True,
    )
    attention.start()
    try:
        low = _work(0, "low")
        high_one = _work(1, "high")
        medium = _work(2, "medium")
        high_two = _work(3, "high")
        assert coordinator.admit_many([low, high_one, medium, high_two])[0]

        assert first_started.wait(2.0)
        # Only the selected reading entered attention; the other three are
        # still pending and produced no effect at all.
        assert processed == [high_one.id]
        assert coordinator.pending == 3

        release_first.set()
        deadline = time.time() + 5.0
        while coordinator.counters["completed"] < 4 and time.time() < deadline:
            time.sleep(0.02)
        assert coordinator.counters["completed"] == 4
        assert processed == [high_one.id, high_two.id, medium.id, low.id]
    finally:
        stop.set()
        coordinator.close_admission()
        coordinator.wake()
        attention.join(timeout=5.0)
        assert not attention.is_alive()


# -- integrated drain ---------------------------------------------------------


def _run_pipeline(factory, state, messages, timeout=15.0):
    queue = MessageQueue(100)
    for message in messages:
        assert queue.append(message)
    stop = threading.Event()
    worker = threading.Thread(
        target=pipeline._worker_loop,
        args=(queue, state, stop),
        daemon=True,
    )
    worker.start()
    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            coordinator = getattr(state, "dispatch_coordinator", None)
            if coordinator is not None and coordinator.counters["completed"] >= len(messages) * 3:
                break
            time.sleep(0.02)
    finally:
        stop.set()
        worker.join(timeout=10.0)
    return state


def _pipeline_state(device_id, user_id, notification_service=None):
    return SimpleNamespace(
        classifications=[],
        events=[],
        alerts=[],
        enriched_events=[],
        notifications=[],
        qos_records=[],
        qos_metrics_service=QoSMetricsService(),
        persistence_service=PersistenceService(),
        event_processing_service=EventProcessingService(
            ThresholdConfig(**THRESHOLDS),
            device_mapping={"CAVA-001": device_id},
            user_id=user_id,
        ),
        notification_service=notification_service,
        backend_config=SimpleNamespace(
            qos_pending_capacity=100,
            qos_high_quota=4,
            qos_medium_quota=2,
            qos_low_quota=1,
            qos_wfq_flow_weights={},
        ),
    )


def test_pipeline_drains_finite_input_without_duplicates(monkeypatch, db_factory):
    device_id, user_id = _seed_device(db_factory)
    monkeypatch.setattr(session_module, "SessionLocal", db_factory)
    state = _pipeline_state(device_id, user_id)

    _run_pipeline(db_factory, state, [_message(), _message()])

    coordinator = state.dispatch_coordinator
    assert coordinator.counters["admitted"] == 6
    assert coordinator.counters["completed"] == 6
    assert coordinator.counters["failed"] == 0
    assert coordinator.counters["pending"] == 0
    assert len(state.classifications) == 6
    assert state.qos_records == []  # no fabricated network-delivery samples

    with db_factory() as db:
        readings = db.query(SensorReadingORM).all()
        assert len(readings) == 6
        assert len({reading.id for reading in readings}) == 6
        assert len({reading.source_message_id for reading in readings}) == 2
        assert {reading.sensor_name for reading in readings} == {
            "temperature", "humidity", "energy",
        }
        assert db.query(TrafficClassificationORM).count() == 6
        assert db.query(QoSMetricORM).count() == 6
        for metric in db.query(QoSMetricORM).all():
            assert metric.processing_version == 2
            assert metric.packet_loss is None and metric.pdr is None
            assert metric.throughput is None and metric.jitter is None
            assert metric.selected_at is not None and metric.persisted_at is not None
            assert metric.finished_at is not None
            assert metric.queue_wait_ms is not None and metric.service_time_ms is not None


def test_one_message_dispatches_each_sensor_before_its_own_effects(monkeypatch, db_factory):
    """Real classification and persistence with barriers and a fake notifier."""
    device_id, user_id = _seed_device(db_factory)
    monkeypatch.setattr(session_module, "SessionLocal", db_factory)
    run_id = uuid.uuid4()
    _seed_run(db_factory, run_id)
    state = _pipeline_state(device_id, user_id)
    coordinator = DispatchCoordinator(TrafficPlanningService(), capacity=10)
    message = _message(temperature=9.5, humidity=82.0, energy="on")
    message.update(scenario="WITH_QOS", run_id=str(run_id))
    pipeline._ingest_message(message, state, coordinator, itertools.count(),
                             pipeline._parse_received_at(message))
    assert coordinator.snapshot()["queues"] == {"high": 1, "medium": 1, "low": 1}
    with db_factory() as db:
        assert db.query(SensorReadingORM).count() == 0
        assert db.query(AlertORM).count() == 0

    first_selected, second_selected = threading.Event(), threading.Event()
    release_first, release_second = threading.Event(), threading.Event()
    trace = []
    original = pipeline._process_work_item

    def process(item, app_state):
        trace.append(("selected", item.sensor_name))
        if len([event for event in trace if event[0] == "selected"]) == 1:
            first_selected.set()
            assert release_first.wait(5)
        elif not second_selected.is_set():
            second_selected.set()
            assert release_second.wait(5)
        result = original(item, app_state)
        trace.append(("attention_done", item.sensor_name))
        return result

    def notify(alerts, app_state):
        for alert in alerts:
            with db_factory() as db:
                persisted = db.get(AlertORM, alert.id)
                assert persisted is not None and persisted.reading_id is not None
            trace.append(("notification_after_commit", str(alert.id)))
        return []

    monkeypatch.setattr(pipeline, "_process_work_item", process)
    monkeypatch.setattr(pipeline, "_notify_alerts", notify)
    stop = threading.Event()
    attention = threading.Thread(target=pipeline._attention_loop,
                                 args=(coordinator, state, stop))
    attention.start()
    try:
        assert first_selected.wait(3)
        assert trace[0] == ("selected", "temperature")
        with db_factory() as db:
            assert db.query(SensorReadingORM).count() == 0
            assert db.query(AlertORM).count() == 0
        release_first.set()
        assert second_selected.wait(5)
        with db_factory() as db:
            rows = db.query(SensorReadingORM).all()
            assert len(rows) == 1 and rows[0].sensor_name == "temperature"
            assert rows[0].temperature == pytest.approx(9.5)
            assert rows[0].humidity is None and rows[0].energy is None
            assert all(alert.reading_id == rows[0].id for alert in db.query(AlertORM))
            assert db.query(QoSMetricORM).count() == 1
        assert any(kind == "notification_after_commit" for kind, _ in trace)
        release_second.set()
        assert coordinator.wait_until_idle(5)
    finally:
        release_first.set()
        release_second.set()
        coordinator.close_admission()
        coordinator.wake()
        attention.join(5)
        assert not attention.is_alive()
    assert [value for kind, value in trace if kind == "selected"] == [
        "temperature", "humidity", "energy",
    ]
    with db_factory() as db:
        rows = db.query(SensorReadingORM).all()
        assert len(rows) == 3
        assert len({r.source_message_id for r in rows}) == 1
        by_sensor = {r.sensor_name: r for r in rows}
        assert by_sensor["humidity"].humidity == pytest.approx(82)
        assert by_sensor["energy"].energy == "on"
        for sensor, priority, queue in (("temperature", "high", "WFQ"),
                                        ("humidity", "medium", "Round Robin"),
                                        ("energy", "low", "FIFO")):
            row = by_sensor[sensor]
            tc = db.query(TrafficClassificationORM).filter_by(reading_id=row.id).one()
            assert (tc.priority.lower(), tc.queue) == (priority, queue)
            metric = db.query(QoSMetricORM).filter_by(classification_id=tc.id).one()
            assert metric.processing_version == 2
            assert metric.queue_wait_ms is not None
            assert metric.service_time_ms is not None
            assert metric.pdr is None


def test_qos_write_failure_does_not_undo_confirmed_reading(monkeypatch, db_factory, caplog):
    device_id, user_id = _seed_device(db_factory)
    monkeypatch.setattr(session_module, "SessionLocal", db_factory)
    state = _pipeline_state(device_id, user_id)
    work = _work(0, "high", sensor="temperature", value=9.5)
    committed = pipeline._process_work_item(work, state)
    assert committed is not None

    def unavailable():
        raise RuntimeError("QoS storage unavailable")

    monkeypatch.setattr(session_module, "SessionLocal", unavailable)
    pipeline._persist_qos_attention(
        work, selected_at=committed, committed_at=committed,
        finished_at=committed, queue_wait_ms=1.0, service_time_ms=2.0,
    )
    assert "reading remains committed" in caplog.text
    with db_factory() as db:
        assert db.get(SensorReadingORM, work.id) is not None
        assert db.query(QoSMetricORM).count() == 0


def test_qos_observation_omits_unmeasurable_latency(monkeypatch, db_factory):
    device_id, user_id = _seed_device(db_factory)
    monkeypatch.setattr(session_module, "SessionLocal", db_factory)
    state = _pipeline_state(device_id, user_id)
    work = _work(0, "high", sensor="temperature", value=9.5)
    committed = pipeline._process_work_item(work, state)
    pipeline._persist_qos_attention(
        work, selected_at=committed, committed_at=committed,
        finished_at=committed, queue_wait_ms=None, service_time_ms=None,
    )
    with db_factory() as db:
        row = db.query(QoSMetricORM).one()
        assert row.latency is None
        assert row.queue_wait_ms is None and row.service_time_ms is None
        assert row.pdr is None and row.packet_loss is None


def test_qos_latency_is_receipt_to_confirmed_commit(monkeypatch, db_factory):
    from dataclasses import replace
    from datetime import timedelta

    device_id, user_id = _seed_device(db_factory)
    monkeypatch.setattr(session_module, "SessionLocal", db_factory)
    state = _pipeline_state(device_id, user_id)
    work = replace(_work(0, "high", sensor="temperature", value=9.5),
                   received_at=NOW, received_monotonic=None)
    assert pipeline._process_work_item(work, state) is not None
    committed = NOW + timedelta(seconds=2)
    pipeline._persist_qos_attention(
        work, selected_at=NOW, committed_at=committed,
        finished_at=committed + timedelta(seconds=1),
        queue_wait_ms=125.0, service_time_ms=3000.0,
    )
    with db_factory() as db:
        row = db.query(QoSMetricORM).one()
        assert row.latency == pytest.approx(2.0)
        assert row.queue_wait_ms == pytest.approx(125)
        assert row.service_time_ms == pytest.approx(3000)
        assert row.processing_version == 2
        assert row.packet_loss is None and row.throughput is None


class _RecordingEventService:
    def __init__(self, alerts=None):
        self.calls = 0
        self.alerts = list(alerts or [])

    def process(self, readings, classification=None):
        self.calls += 1
        return {
            "events": [],
            "alerts": list(self.alerts),
            "event_count": 0,
            "alert_count": len(self.alerts),
        }


class _ForbiddenNotificationService:
    def __init__(self):
        self.calls = 0

    def process(self, alert):
        self.calls += 1
        raise AssertionError("notifications must not be sent before a commit")


class _FailingPersistence(PersistenceService):
    def persist_work_item(self, *args, **kwargs):
        raise RuntimeError("database unavailable")


def test_persistence_failure_never_notifies(monkeypatch, db_factory):
    device_id, user_id = _seed_device(db_factory)
    monkeypatch.setattr(session_module, "SessionLocal", db_factory)
    alert = Alert(
        id=uuid.uuid4(),
        device_id=device_id,
        user_id=user_id,
        type="TEMPERATURE_EXCEEDED",
        message="warm",
        criticality=9.0,
        acknowledged=False,
        created_at=datetime.now(timezone.utc),
    )
    state = _pipeline_state(device_id, user_id)
    state.persistence_service = _FailingPersistence()
    state.event_processing_service = _RecordingEventService([alert])
    notifications = _ForbiddenNotificationService()
    state.notification_service = notifications

    work = _work(0, "high", sensor="temperature", value=9.5)
    with pytest.raises(RuntimeError, match="database unavailable"):
        pipeline._process_work_item(work, state)

    assert notifications.calls == 0
    assert state.alerts == []
    assert state.events == []
    with db_factory() as db:
        assert db.query(SensorReadingORM).count() == 0
        assert db.query(TrafficClassificationORM).count() == 0


@pytest.mark.parametrize("failure", ["flush", "commit", "no_persistence", None])
def test_session_effects_are_visible_only_after_confirmed_commit(
    monkeypatch, db_factory, failure
):
    device_id, user_id = _seed_device(db_factory)
    monkeypatch.setattr(session_module, "SessionLocal", db_factory)
    state = _pipeline_state(device_id, user_id)
    original = state.persistence_service.persist_work_item

    def persist(*args, **kwargs):
        rows = original(*args, **kwargs)
        # A flush is not a commit: neither session endpoint may see this yet.
        assert state.alerts == [] and state.events == []
        if failure == "flush":
            raise RuntimeError("write failed after flush")
        return rows

    monkeypatch.setattr(state.persistence_service, "persist_work_item", persist)
    if failure == "commit":
        def fail_commit(session):
            assert state.alerts == [] and state.events == []
            raise RuntimeError("commit failed")

        sqlalchemy_event.listen(db_factory, "before_commit", fail_commit)
    elif failure == "no_persistence":
        state.persistence_service = None

    work = _work(0, "high", sensor="temperature", value=9.5)
    if failure in ("flush", "commit"):
        with pytest.raises(RuntimeError):
            pipeline._process_work_item(work, state)
    else:
        pipeline._process_work_item(work, state)
    with db_factory() as db:
        expected = 1 if failure is None else 0
        assert len(state.events) == expected
        assert len(state.alerts) == expected
        assert db.query(AlertORM).count() == expected
        assert db.query(SensorReadingORM).count() == expected
        if expected:
            assert state.alerts[0].id == db.query(AlertORM).one().id


def test_replayed_work_skips_events_and_duplicates(monkeypatch, db_factory):
    device_id, user_id = _seed_device(db_factory)
    monkeypatch.setattr(session_module, "SessionLocal", db_factory)
    state = _pipeline_state(device_id, user_id)
    state.notification_service = None
    events = _RecordingEventService()
    state.event_processing_service = events

    work = _work(0, "low", sensor="temperature", value=3.0)
    pipeline._process_work_item(work, state)
    pipeline._process_work_item(work, state)

    assert events.calls == 1
    with db_factory() as db:
        assert db.query(SensorReadingORM).count() == 1
        assert db.query(TrafficClassificationORM).count() == 1


class _FailingChannelService:
    """The channel is down: processing raises after the reading committed."""

    def __init__(self):
        self.calls = 0

    def process_and_persist(self, alert, db, **kwargs):
        self.calls += 1
        raise RuntimeError("channel unavailable")

    def resolve_recipient(self, alert):  # pragma: no cover - never reached
        return None

    def resolve_message(self, alert):
        return alert.message


def test_channel_failure_keeps_confirmed_reading_and_alert(monkeypatch, db_factory):
    device_id, user_id = _seed_device(db_factory)
    from app.auth.sessions import active_sessions

    monkeypatch.setattr(active_sessions, "_expires_at", {})
    with db_factory() as db:
        db.get(UserORM, user_id).role = "admin"
        db.commit()
    active_sessions.login(user_id, 3600)
    monkeypatch.setattr(session_module, "SessionLocal", db_factory)
    alert = Alert(
        id=uuid.uuid4(),
        device_id=device_id,
        user_id=user_id,
        type="TEMPERATURE_EXCEEDED",
        message="warm",
        criticality=9.0,
        acknowledged=False,
        created_at=datetime.now(timezone.utc),
    )
    state = _pipeline_state(device_id, user_id)
    state.event_processing_service = _RecordingEventService([alert])
    channels = _FailingChannelService()
    state.notification_service = channels

    work = _work(0, "high", sensor="temperature", value=9.5)
    pipeline._process_work_item(work, state)

    assert channels.calls == 1
    with db_factory() as db:
        # The confirmed transaction is never rolled back by a channel error.
        assert db.query(SensorReadingORM).count() == 1
        assert db.query(AlertORM).count() == 1
        assert db.query(NotificationORM).count() == 0


def test_pending_work_keeps_scenario_sealed_at_reception(monkeypatch, db_factory):
    """Closing the run must not reassign already-received work (AC6)."""
    device_id, user_id = _seed_device(db_factory)
    monkeypatch.setattr(session_module, "SessionLocal", db_factory)
    state = _pipeline_state(device_id, user_id)
    state.notification_service = None
    state.event_processing_service = _RecordingEventService()
    sealed_run = uuid.uuid4()
    with db_factory() as db:
        with db.begin():
            db.add(
                ExperimentRunORM(
                    id=sealed_run,
                    scenario="WITH_QOS",
                    started_at=datetime.now(timezone.utc),
                )
            )

    message = _message()
    message["scenario"] = "WITH_QOS"
    message["run_id"] = str(sealed_run)
    # The experiment ends before the admitted reading is attended.
    active.clear_active_run()

    _run_pipeline(db_factory, state, [message])

    with db_factory() as db:
        readings = db.query(SensorReadingORM).all()
        assert len(readings) == 3
        assert all(reading.run_id == sealed_run for reading in readings)
        # The classification belongs to the same sealed reading.
        assert {
            tc.reading_id for tc in db.query(TrafficClassificationORM).all()
        } == {reading.id for reading in readings}


# -- lifecycle and metrics ----------------------------------------------------


def test_drain_rejects_only_the_closing_run():
    coordinator = DispatchCoordinator(TrafficPlanningService(), capacity=10)
    closing_run, next_run = uuid.uuid4(), uuid.uuid4()
    closing = _work(0, run_id=closing_run)
    following = _work(1, run_id=next_run)
    assert coordinator.admit(closing)

    coordinator.begin_drain(closing_run)
    accepted, rejected = coordinator.admit_many([_work(2, run_id=closing_run), following])

    assert accepted == [following]
    assert [item.run_id for item in rejected] == [closing_run]
    assert coordinator.snapshot()["draining"] is True
    assert coordinator.draining_run_id == closing_run

    # Both admitted readings are still attended; nothing is reassigned.
    for _ in range(2):
        assert coordinator.select_next() is not None
        assert coordinator.wait_until_idle(0.0) is False  # one still in flight
        coordinator.finish(success=True)
    assert coordinator.wait_until_idle(1.0) is True
    coordinator.end_drain()
    assert coordinator.is_draining is False
    assert coordinator.snapshot()["draining_run_id"] is None


def test_wait_until_idle_times_out_with_pending_work():
    coordinator = DispatchCoordinator(TrafficPlanningService(), capacity=10)
    assert coordinator.admit(_work(0))
    assert coordinator.wait_until_idle(0.0) is False
    assert coordinator.select_next() is not None
    coordinator.finish(success=True)
    assert coordinator.wait_until_idle(1.0) is True


@pytest.mark.parametrize("scenario", ["WITH_QOS", "WITHOUT_QOS"])
def test_finish_drains_queued_and_ingesting_messages_before_closing(monkeypatch, db_factory, scenario):
    """A barrier covers transport, ingestion, dispatch and committed attention."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.auth.dependencies import AuthenticatedUser, get_current_user
    from app.database.infrastructure.session import get_db
    from app.experiments.api import router
    from app.security.dependencies import require_admin
    import app.experiments.api as experiment_api

    device_id, user_id = _seed_device(db_factory)
    run_id = uuid.uuid4()
    with db_factory() as db:
        with db.begin():
            db.add(ExperimentRunORM(id=run_id, scenario=scenario, started_at=NOW))
    monkeypatch.setattr(session_module, "SessionLocal", db_factory)
    monkeypatch.setattr(experiment_api, "stop_worker", lambda _id: None)
    active.set_active_run(run_id, scenario)
    queue = MessageQueue(10)
    state = _pipeline_state(device_id, user_id)
    coordinator = DispatchCoordinator(TrafficPlanningService(), capacity=20)
    state.dispatch_coordinator = coordinator
    app = FastAPI()
    app.include_router(router)
    app.state.message_queue = queue
    app.state.dispatch_coordinator = coordinator
    app.state.backend_config = SimpleNamespace(qos_drain_timeout_s=5.0)

    def db_override():
        with db_factory() as db:
            yield db

    user = AuthenticatedUser(id=uuid.uuid4(), email="admin@example.com",
                             name="Admin", role="admin", is_active=True)
    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_admin] = lambda: user
    processing_started, release_ingest = threading.Event(), threading.Event()
    attention_started, release_attention = threading.Event(), threading.Event()
    original_ingest, original_process = pipeline._ingest_message, pipeline._process_work_item

    def blocked_ingest(*args, **kwargs):
        if not processing_started.is_set():
            processing_started.set()
            assert release_ingest.wait(5)
        return original_ingest(*args, **kwargs)

    def blocked_attention(*args, **kwargs):
        if not attention_started.is_set():
            attention_started.set()
            assert release_attention.wait(5)
        return original_process(*args, **kwargs)

    monkeypatch.setattr(pipeline, "_ingest_message", blocked_ingest)
    monkeypatch.setattr(pipeline, "_process_work_item", blocked_attention)
    first, second, late = _message(), _message(), _message()
    assert queue.append_received(first)
    stop = threading.Event()
    worker = threading.Thread(target=pipeline._worker_loop, args=(queue, state, stop))
    worker.start()
    finish_thread = None
    try:
        assert processing_started.wait(3)
        assert queue.append_received(second)
        result = []
        with TestClient(app) as client:
            finish_thread = threading.Thread(
                target=lambda: result.append(client.post(f"/experiment-runs/{run_id}/finish"))
            )
            finish_thread.start()
            deadline = time.monotonic() + 3
            while not coordinator.is_draining and time.monotonic() < deadline:
                threading.Event().wait(0.01)
            assert coordinator.is_draining
            assert not queue.append_received(late)
            assert late["run_id"] == str(run_id)
            assert finish_thread.is_alive()
            assert client.post(f"/experiment-runs/{run_id}/finish").status_code == 409
            assert client.get(f"/experiment-runs/{run_id}").json()["finished_at"] is None
            release_ingest.set()
            assert attention_started.wait(3)
            assert finish_thread.is_alive()
            release_attention.set()
            finish_thread.join(8)
            assert not finish_thread.is_alive()
            assert result[0].status_code == 200, result[0].text
            assert result[0].json()["finished_at"] is not None
        with db_factory() as db:
            readings = db.query(SensorReadingORM).filter_by(run_id=run_id).all()
            assert len(readings) == 6
            assert len({row.source_message_id for row in readings}) == 2
            assert db.query(TrafficClassificationORM).count() == (6 if scenario == "WITH_QOS" else 0)
            assert db.query(QoSMetricORM).count() == (6 if scenario == "WITH_QOS" else 0)
        assert coordinator.counters["completed"] == 6
        assert coordinator.counters["rejected"] == 0
        assert queue.rejected == 1
    finally:
        release_ingest.set()
        release_attention.set()
        stop.set()
        worker.join(8)
        if finish_thread is not None:
            finish_thread.join(8)
        active.clear_active_run()
        assert not worker.is_alive()


def test_shutdown_timeout_cancels_pending_and_waits_for_inflight(monkeypatch, caplog):
    coordinator = DispatchCoordinator(TrafficPlanningService(), capacity=10)
    selected = threading.Event()
    release = threading.Event()
    processed = []
    state = SimpleNamespace(dispatch_coordinator=coordinator)
    queue = MessageQueue(10)
    worker = pipeline.AcquisitionPipeline(queue, state, shutdown_timeout=0)
    first, second, third = (_work(i, priority) for i, priority in enumerate(("high", "medium", "low")))
    assert len(coordinator.admit_many([first, second, third])[0]) == 3

    def blocked_process(item, _state):
        processed.append(item.id)
        selected.set()
        assert release.wait(5)

    monkeypatch.setattr(pipeline, "_process_work_item", blocked_process)
    worker._thread = threading.Thread(
        target=pipeline._attention_loop,
        args=(coordinator, state, worker._stop_event),
    )
    worker._thread.start()
    assert selected.wait(2)
    assert queue.append({"topic": "fixture", "run_id": None})
    stopper = threading.Thread(target=worker.stop)
    stopper.start()
    try:
        deadline = time.monotonic() + 2
        while coordinator.counters["cancelled"] != 2 and time.monotonic() < deadline:
            threading.Event().wait(0.01)
        assert coordinator.counters["cancelled"] == 2
        assert coordinator.pending == 0
        assert coordinator.in_flight == 1
        assert stopper.is_alive()
        assert len(queue) == 0
        assert "Cancelled 1 pending transport messages" in caplog.text
    finally:
        release.set()
        stopper.join(5)
    assert not stopper.is_alive()
    assert processed == [first.id]
    assert coordinator.counters["completed"] == 1
    assert coordinator.counters["failed"] == 0
    assert coordinator.counters["cancelled"] == 2


def test_failed_attention_is_counted_as_failure_not_success(monkeypatch):
    coordinator = DispatchCoordinator(TrafficPlanningService(), capacity=10)
    state = SimpleNamespace()
    stop = threading.Event()
    timings = []

    def failing_process(work_item, app_state):
        raise RuntimeError("attention failed")

    monkeypatch.setattr(pipeline, "_process_work_item", failing_process)
    monkeypatch.setattr(
        pipeline,
        "_record_attention_timing",
        lambda work_item, **kwargs: timings.append((work_item.id, kwargs)),
    )
    attention = threading.Thread(
        target=pipeline._attention_loop,
        args=(coordinator, state, stop),
        daemon=True,
    )
    attention.start()
    try:
        work = _work(0, run_id=uuid.uuid4())
        assert coordinator.admit(work)
        deadline = time.time() + 5.0
        while coordinator.counters["failed"] < 1 and time.time() < deadline:
            time.sleep(0.02)
        assert coordinator.counters["failed"] == 1
        assert coordinator.counters["completed"] == 0
        assert timings and timings[0][0] == work.id
        assert timings[0][1]["success"] is False
    finally:
        stop.set()
        coordinator.close_admission()
        coordinator.wake()
        attention.join(timeout=5.0)
        assert not attention.is_alive()


def _seed_run(factory, run_id):
    with factory() as db:
        with db.begin():
            db.add(
                ExperimentRunORM(
                    id=run_id,
                    scenario="WITH_QOS",
                    started_at=datetime.now(timezone.utc),
                )
            )


def test_attention_timing_records_measured_intervals_after_attention(
    monkeypatch, db_factory
):
    run_id = uuid.uuid4()
    _seed_run(db_factory, run_id)
    monkeypatch.setattr(session_module, "SessionLocal", db_factory)
    work = _work(0, run_id=run_id)

    pipeline._record_attention_timing(
        work, queue_wait_ms=12.5, service_time_ms=34.25, success=True
    )
    pipeline._record_attention_timing(
        work, queue_wait_ms=None, service_time_ms=None, success=False
    )

    with db_factory() as db:
        metrics = {
            metric.metric_type: metric.value
            for metric in db.query(ExperimentMetricORM).filter_by(run_id=run_id)
        }
    # Two measured timings and one real failure; unavailable values are absent.
    assert metrics["queue_wait_ms"] == pytest.approx(12.5)
    assert metrics["service_time_ms"] == pytest.approx(34.25)
    assert metrics["readings_failed"] == pytest.approx(1.0)
    assert "readings_persisted" not in metrics


def test_admission_metrics_are_recorded_for_run(monkeypatch, db_factory):
    device_id, user_id = _seed_device(db_factory)
    run_id = uuid.uuid4()
    _seed_run(db_factory, run_id)
    monkeypatch.setattr(session_module, "SessionLocal", db_factory)
    state = _pipeline_state(device_id, user_id)
    state.notification_service = None

    message = _message()
    message["scenario"] = "WITH_QOS"
    message["run_id"] = str(run_id)
    _run_pipeline(db_factory, state, [message])

    with db_factory() as db:
        types = {
            metric.metric_type
            for metric in db.query(ExperimentMetricORM).filter_by(run_id=run_id)
        }
    assert "readings_admitted" in types
    assert "readings_persisted" in types
    assert "queue_wait_ms" in types
    assert "service_time_ms" in types


def test_rejected_admission_is_observable(monkeypatch, db_factory):
    run_id = uuid.uuid4()
    _seed_run(db_factory, run_id)
    monkeypatch.setattr(session_module, "SessionLocal", db_factory)
    state = _pipeline_state(uuid.uuid4(), uuid.uuid4())
    state.backend_config = SimpleNamespace(
        qos_pending_capacity=1,
        qos_high_quota=4,
        qos_medium_quota=2,
        qos_low_quota=1,
        qos_wfq_flow_weights={},
    )

    message = _message()
    message["scenario"] = "WITH_QOS"
    message["run_id"] = str(run_id)
    # The attention never runs here: admission stays saturated on purpose.
    coordinator = SimpleNamespace(
        admit=lambda item: False,
        capacity=1,
    )
    pipeline._ingest_message(
        message, state, coordinator, iter(range(10)), datetime.now(timezone.utc)
    )

    with db_factory() as db:
        rows = db.query(ExperimentMetricORM).filter_by(run_id=run_id).all()
    # Three sensors were normalised and every one was rejected; the counter
    # is real and no reading was persisted.
    rejected = [row for row in rows if row.metric_type == "readings_rejected"]
    assert len(rejected) == 3
    assert all(row.value == pytest.approx(1.0) for row in rejected)
    assert not [row for row in rows if row.metric_type == "readings_admitted"]
