from datetime import datetime, timezone
from uuid import uuid4

from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification
from app.qos import WFQScheduler
from app.qos.tests.wfq_reference import ReferencePacket, wfq_reference_order
from app.qos.domain.work_item import WorkItem


NOW = datetime(2026, 11, 19, tzinfo=timezone.utc)


def _item(device, sequence):
    work_id = uuid4()
    classification = TrafficClassification(
        id=uuid4(), reading_id=work_id, criticality=9, priority="high",
        queue="WFQ", classification_time=NOW, timestamp=NOW,
    )
    return WorkItem.from_reading(
        NormalizedReading(device, "cold_room", "temperature", 9.5, NOW.isoformat(), 9.5),
        id=work_id, source_message_id=uuid4(), sequence=sequence,
        scenario="WITH_QOS", run_id=None, admitted_at=NOW,
        admitted_monotonic=float(sequence), classification=classification,
    )


def test_wfq_matches_independent_oracle_for_equal_weights_and_stable_ties():
    items = [_item("A", 0), _item("B", 1), _item("A", 2), _item("B", 3)]
    scheduler = WFQScheduler()
    for item in items:
        scheduler.enqueue(item)
    expected = wfq_reference_order([
        ReferencePacket(item.flow_id, 0, item.sequence, 1, str(item.id)) for item in items
    ])
    assert [str(scheduler.dequeue().id) for _ in items] == expected


def test_wfq_matches_two_to_one_weight_oracle_and_preserves_flow_fifo():
    items = [_item("A", 0), _item("B", 1), _item("A", 2), _item("A", 3), _item("B", 4)]
    scheduler = WFQScheduler(flow_weights={("A", "temperature"): 2})
    for item in items:
        scheduler.enqueue(item)
    expected = wfq_reference_order([
        ReferencePacket(
            item.flow_id, 0, item.sequence,
            2 if item.device_code == "A" else 1, str(item.id),
        )
        for item in items
    ])
    selected = [scheduler.dequeue() for _ in items]
    assert [str(item.id) for item in selected] == expected
    assert [item.sequence for item in selected if item.device_code == "A"] == [0, 2, 3]


def test_reactivated_flow_does_not_reuse_stale_finish_tag():
    scheduler = WFQScheduler()
    a1, b1, b2, a2 = _item("A", 0), _item("B", 1), _item("B", 2), _item("A", 3)
    scheduler.enqueue(a1)
    scheduler.enqueue(b1)
    assert scheduler.dequeue() is a1
    scheduler.enqueue(b2)
    assert scheduler.dequeue() is b1
    assert scheduler.dequeue() is b2
    scheduler.enqueue(a2)
    assert scheduler.dequeue() is a2
