from datetime import datetime, timezone
from uuid import uuid4

from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification
from app.qos import RoundRobinScheduler
from app.qos.domain.work_item import WorkItem


NOW = datetime(2026, 11, 19, tzinfo=timezone.utc)


def _item(device_code: str, sensor_name: str, sequence: int) -> WorkItem:
    work_id = uuid4()
    classification = TrafficClassification(
        id=uuid4(), reading_id=work_id, criticality=6, priority="medium",
        queue="Round Robin", classification_time=NOW, timestamp=NOW,
    )
    return WorkItem.from_reading(
        NormalizedReading(
            device_code, "cold_room", sensor_name, 80.0, NOW.isoformat(), 80.0,
        ),
        id=work_id, source_message_id=uuid4(), sequence=sequence,
        scenario="WITH_QOS", run_id=None, admitted_at=NOW,
        admitted_monotonic=float(sequence), classification=classification,
    )


def test_rr_rotates_active_flows_and_keeps_fifo_within_each_flow():
    scheduler = RoundRobinScheduler()
    a1, a2, a3 = (_item("CAVA-001", "humidity", sequence) for sequence in (1, 3, 5))
    b1, b2 = (_item("CAVA-002", "humidity", sequence) for sequence in (2, 4))

    for item in (a1, a2, b1, a3, b2):
        scheduler.enqueue(item)

    assert scheduler.slot_names == [
        ("CAVA-001", "humidity"), ("CAVA-002", "humidity"),
    ]
    assert [scheduler.dequeue() for _ in range(5)] == [a1, b1, a2, b2, a3]
    assert scheduler.dequeue() is None
    assert scheduler.slot_names == []


def test_new_flow_joins_the_tail_and_empty_flows_are_removed():
    scheduler = RoundRobinScheduler()
    a1, a2 = (_item("CAVA-001", "humidity", sequence) for sequence in (1, 3))
    b1 = _item("CAVA-002", "humidity", 2)
    c1 = _item("CAVA-003", "humidity", 4)
    scheduler.enqueue(a1)
    scheduler.enqueue(b1)

    assert scheduler.dequeue() is a1
    scheduler.enqueue(c1)
    scheduler.enqueue(a2)
    assert scheduler.slot_names == [
        ("CAVA-002", "humidity"),
        ("CAVA-003", "humidity"),
        ("CAVA-001", "humidity"),
    ]
    assert [scheduler.dequeue() for _ in range(4)] == [b1, c1, a2, None]
    assert scheduler.size() == 0
