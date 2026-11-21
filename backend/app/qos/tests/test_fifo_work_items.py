from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification
from app.qos import FIFOScheduler, TrafficPlanningService
from app.qos.domain.work_item import WorkItem


NOW = datetime(2026, 11, 19, tzinfo=timezone.utc)


def _item(sequence: int, priority: str = "low") -> WorkItem:
    queues = {"low": "FIFO", "medium": "Round Robin", "high": "WFQ"}
    work_id = uuid4()
    classification = TrafficClassification(
        id=uuid4(), reading_id=work_id,
        criticality={"low": 3.0, "medium": 5.0, "high": 9.0}[priority], priority=priority,
        queue=queues[priority], classification_time=NOW, timestamp=NOW,
    )
    return WorkItem.from_reading(
        NormalizedReading(
            "CAVA-001", "cold_room", "energy", 1.0, NOW.isoformat(), "on",
        ),
        id=work_id, source_message_id=uuid4(), sequence=sequence,
        scenario="WITH_QOS", run_id=None, admitted_at=NOW,
        admitted_monotonic=float(sequence), classification=classification,
    )


def test_low_work_items_leave_fifo_in_admission_order():
    scheduler = FIFOScheduler()
    first, second, third = (_item(sequence) for sequence in (4, 7, 9))

    for item in (first, second, third):
        scheduler.enqueue(item)

    assert scheduler.size() == 3
    assert [scheduler.dequeue(), scheduler.dequeue(), scheduler.dequeue()] == [
        first, second, third,
    ]
    assert scheduler.dequeue() is None
    assert scheduler.is_empty()


@pytest.mark.parametrize("priority", ("medium", "high"))
def test_fifo_rejects_a_work_item_from_another_priority(priority):
    with pytest.raises(ValueError, match="does not match"):
        FIFOScheduler().enqueue(_item(0, priority))


def test_planner_routes_low_work_items_and_keeps_their_context():
    item = _item(11)
    service = TrafficPlanningService()

    assert service.plan(item) is item
    assert service.get_queue("low") == [item]
    selected = service.dequeue("low")
    assert selected is item
    assert selected.to_reading().sensor_name == "energy"
    assert selected.classification.reading_id == selected.id


def test_planner_rejects_non_work_or_legacy_classification_input():
    with pytest.raises(TypeError, match="WorkItem"):
        TrafficPlanningService().plan(object())
