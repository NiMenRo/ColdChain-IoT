"""T2: immutable work per sensor, without scheduler/ORM/runtime side effects."""

import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.acquisition.normalizer import NormalizedReading, TelemetryNormalizer
from app.classification import (
    ClassificationService,
    CriticalityCalculator,
    PriorityAssigner,
    RiskMatrixEvaluator,
)
from app.qos.domain.work_item import WorkItem


NOW = datetime(2026, 11, 19, 12, tzinfo=timezone.utc)


def _reading(sensor="temperature", value=9.5, raw_value=9.5):
    return NormalizedReading(
        device_code="CAVA-001", device_type="cold_room", sensor_name=sensor,
        value=value, timestamp=NOW.isoformat(), raw_value=raw_value,
    )


def _classify(reading):
    criteria = RiskMatrixEvaluator().evaluate(reading)
    return ClassificationService(
        calculator=CriticalityCalculator(), assigner=PriorityAssigner(),
    ).classify(
        reading, criteria.impact, criteria.urgency, criteria.risk,
    )


def _make_work(**overrides):
    reading = overrides.pop("reading", _reading())
    kwargs = {
        "source_message_id": uuid4(), "sequence": 0,
        "scenario": "WITH_QOS", "run_id": uuid4(),
        "admitted_at": NOW, "admitted_monotonic": 12.5,
        "received_at": NOW - timedelta(milliseconds=10),
        "received_monotonic": 12.49,
        "classification": _classify(reading),
    }
    kwargs.update(overrides)
    return WorkItem.from_reading(reading, **kwargs)


def test_three_sensors_share_origin_but_keep_independent_classifications():
    message = {
        "device_origin": {"device_code": "CAVA-001", "device_type": "cold_room"},
        "payload": {
            "temperature": 9.5, "humidity": 82.0, "energy": "on",
            "timestamp": NOW.isoformat(),
        },
    }
    readings = TelemetryNormalizer().normalize(message)
    message_id, run_id = uuid4(), uuid4()
    items = [
        _make_work(
            reading=reading, source_message_id=message_id, run_id=run_id,
            sequence=sequence,
        )
        for sequence, reading in enumerate(readings)
    ]
    assert len({item.id for item in items}) == 3
    assert {item.source_message_id for item in items} == {message_id}
    assert {item.run_id for item in items} == {run_id}
    assert [item.sequence for item in items] == [0, 1, 2]
    assert [item.sensor_name for item in items] == ["temperature", "humidity", "energy"]
    assert [item.priority for item in items] == ["high", "medium", "low"]
    assert [item.classification.queue for item in items] == ["WFQ", "Round Robin", "FIFO"]
    assert [item.classification.criticality for item in items] == [9, 6, 3]
    assert all(item.classification.reading_id == item.id for item in items)
    assert [item.flow_id for item in items] == [
        ("CAVA-001", "temperature"), ("CAVA-001", "humidity"), ("CAVA-001", "energy"),
    ]


def test_input_mutation_does_not_change_the_work_snapshot():
    reading = _reading()
    classification = _classify(reading)
    old_reading_id = classification.reading_id
    item = _make_work(reading=reading, classification=classification)
    assert classification.reading_id == old_reading_id
    reading.value = 1.0
    reading.device_code = "OTHER"
    classification.priority = "low"
    classification.criticality = 3
    classification.reading_id = uuid4()
    assert item.value == 9.5
    assert item.device_code == "CAVA-001"
    assert item.priority == "high"
    assert item.classification.criticality == 9
    assert item.classification.reading_id == item.id


@pytest.mark.parametrize("field,value", [
    ("id", uuid4()), ("source_message_id", uuid4()), ("run_id", uuid4()),
    ("scenario", "WITHOUT_QOS"), ("sequence", 100),
    ("sensor_name", "energy"), ("admitted_monotonic", 99.0),
])
def test_context_cannot_be_reassigned(field, value):
    item = _make_work()
    with pytest.raises(FrozenInstanceError):
        setattr(item, field, value)


def test_classification_snapshot_cannot_be_reassigned():
    item = _make_work()
    with pytest.raises(FrozenInstanceError):
        item.classification.priority = "low"


def test_adapters_are_fresh_objects_and_preserve_work_identity():
    item = _make_work(id=uuid4())
    reading = item.to_reading()
    classification = item.classification.to_classification()
    assert isinstance(reading, NormalizedReading)
    assert reading == item.to_reading()
    assert reading is not item.to_reading()
    assert classification == item.classification.to_classification()
    assert classification is not item.classification.to_classification()
    assert classification.reading_id == item.id
    reading.value = 0.0
    classification.priority = "low"
    assert item.value == 9.5
    assert item.priority == "high"


def test_without_qos_has_no_priority_or_classification():
    item = _make_work(scenario="WITHOUT_QOS", classification=None)
    assert item.classification is None
    assert item.priority is None
    assert item.to_reading().value == 9.5


def test_legacy_context_and_unknown_reception_times_are_not_fabricated():
    item = _make_work(run_id=None, received_at=None, received_monotonic=None)
    assert item.run_id is None
    assert item.scenario == "WITH_QOS"
    assert item.received_at is None
    assert item.received_monotonic is None
    assert item.admitted_at == NOW


def test_context_does_not_follow_the_active_experiment():
    # Changing an external holder must not affect a work item already admitted.
    holder = {"run_id": uuid4(), "scenario": "WITH_QOS"}
    item = _make_work(**holder)
    original_run_id = item.run_id
    holder.update(run_id=uuid4(), scenario="WITHOUT_QOS")
    assert item.run_id == original_run_id
    assert item.scenario == "WITH_QOS"


def test_admission_clocks_are_explicit_and_utc_normalized():
    colombia = timezone(timedelta(hours=-5))
    item = _make_work(
        admitted_at=NOW.astimezone(colombia),
        received_at=(NOW - timedelta(milliseconds=10)).astimezone(colombia),
    )
    assert item.admitted_at == NOW
    assert item.admitted_at.tzinfo == timezone.utc
    assert item.received_at.tzinfo == timezone.utc
    assert item.received_monotonic == 12.49
    assert item.admitted_monotonic == 12.5


@pytest.mark.parametrize("overrides,error", [
    ({"id": "bad"}, TypeError),
    ({"source_message_id": "bad"}, TypeError),
    ({"run_id": "bad"}, TypeError),
    ({"sequence": True}, TypeError),
    ({"sequence": -1}, ValueError),
    ({"scenario": "UNKNOWN"}, ValueError),
    ({"classification": None}, TypeError),
    ({"scenario": "WITHOUT_QOS"}, ValueError),
    ({"admitted_at": NOW.replace(tzinfo=None)}, ValueError),
    ({"received_at": NOW.replace(tzinfo=None)}, ValueError),
    ({"admitted_monotonic": float("inf")}, ValueError),
    ({"received_monotonic": float("nan")}, ValueError),
    ({"received_monotonic": 13.0}, ValueError),
    ({"admitted_monotonic": True}, TypeError),
    ({"classification": object()}, TypeError),
])
def test_rejects_invalid_admission_context(overrides, error):
    with pytest.raises(error):
        _make_work(**overrides)


@pytest.mark.parametrize("field,value,error", [
    ("value", float("nan"), ValueError),
    ("value", True, TypeError),
    ("raw_value", {"nested": []}, TypeError),
    ("raw_value", float("inf"), ValueError),
    ("sensor_name", "unsupported", ValueError),
    ("device_code", "", ValueError),
    ("timestamp", "invalid", ValueError),
])
def test_rejects_invalid_or_mutable_reading_data(field, value, error):
    item = _make_work()
    with pytest.raises(error):
        replace(item, **{field: value})


def test_rejects_classification_for_another_work_or_timestamp():
    item = _make_work()
    with pytest.raises(ValueError, match="reading_id"):
        replace(item, classification=replace(item.classification, reading_id=uuid4()))
    with pytest.raises(ValueError, match="timestamp"):
        replace(item, classification=replace(
            item.classification, timestamp=NOW + timedelta(seconds=1),
        ))


def test_rejects_inconsistent_priority_queue_mapping():
    item = _make_work()
    with pytest.raises(ValueError, match="queue"):
        replace(item.classification, queue="FIFO")


def test_module_has_no_runtime_or_orm_import_side_effects():
    result = subprocess.run(
        [sys.executable, "-B", "-c", (
            "import sys; from app.qos.domain.work_item import WorkItem; "
            "forbidden = ['sqlalchemy', 'paho', 'main', "
            "'app.acquisition.pipeline', 'app.experiments.active']; "
            "assert not any(name in sys.modules for name in forbidden), "
            "[name for name in forbidden if name in sys.modules]"
        )],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
