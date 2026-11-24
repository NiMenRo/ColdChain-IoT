from collections import Counter
from fractions import Fraction

import pytest

from app.qos import WFQScheduler
from app.qos.tests.test_wfq_work_items import _item
from app.qos.tests.wfq_reference import ReferencePacket, wfq_reference_order


def test_saturated_bands_match_independent_tags_and_two_three_share():
    scheduler = WFQScheduler()
    items = [_item(f"device-{i}", 2 * i + c - 8, c)
             for i in range(120) for c in (8, 9)]
    for item in items:
        scheduler.enqueue(item)
    expected = wfq_reference_order([
        ReferencePacket(scheduler.band_for(item), 0, item.sequence,
                        item.classification.criticality - 6, str(item.id))
        for item in items
    ])
    selected = [scheduler.dequeue() for _ in range(120)]
    assert [str(item.id) for item in selected] == expected[:120]
    assert Counter(scheduler.band_for(item) for item in selected) == {
        "H8": 48, "H9": 72,
    }
    for band in ("H8", "H9"):
        sequences = [item.sequence for item in selected if scheduler.band_for(item) == band]
        assert sequences == sorted(sequences)


def test_same_band_is_fifo_across_devices_and_sensors():
    scheduler = WFQScheduler()
    items = [_item("A", 0, 8), _item("A", 1, 8), _item("B", 2, 8)]
    for item in items:
        scheduler.enqueue(item)
    assert [scheduler.dequeue() for _ in items] == items


def test_ties_use_global_admission_not_band_name():
    scheduler = WFQScheduler(band_weights={"H8": 1, "H9": 1})
    items = [_item("A", 0, 9), _item("B", 1, 8)]
    for item in items:
        scheduler.enqueue(item)
    assert [scheduler.dequeue() for _ in items] == items


def test_gps_reactivation_retains_fluid_work_after_packet_queue_empties():
    scheduler = WFQScheduler(band_weights={"H8": 1, "H9": 3})
    h9, h7, h9_new = _item("A", 0, 9), _item("B", 1, 8), _item("C", 2, 9)
    scheduler.enqueue(h9)
    scheduler.enqueue(h7)
    assert scheduler.dequeue() is h9
    assert scheduler.virtual_time == 0.25
    scheduler.enqueue(h9_new)
    # H9 has no packet queued after dequeue, but its GPS work was not done.
    # The new finish must be 1/3+1/3, not V+1/3.
    assert scheduler._items[-1][0] == Fraction(2, 3)
    assert scheduler.dequeue() is h9_new
    assert scheduler.virtual_time == 0.5
    assert scheduler.dequeue() is h7
    assert scheduler.virtual_time == 1
    assert scheduler.dequeue() is None


def test_gps_removes_weight_at_fluid_completion_within_opportunity():
    scheduler = WFQScheduler(band_weights={"H8": 1, "H9": 3})
    scheduler.enqueue(_item("A", 0, 9))
    scheduler.enqueue(_item("B", 1, 8))
    scheduler.dequeue()
    scheduler.dequeue()
    # A naive single increment using packet-active weights gives 1.25,
    # whereas GPS completes both units at V=1.
    assert scheduler.virtual_time == 1
    item = _item("C", 2, 9)
    scheduler.enqueue(item)
    assert scheduler._items[0][0] == Fraction(4, 3)
    assert scheduler.dequeue() is item


@pytest.mark.parametrize("criticality,band", [
    (8, "H8"), (8.99, "H8"), (9, "H9"),
])
def test_boundaries(criticality, band):
    assert WFQScheduler.band_for(_item("A", 0, criticality)) == band


@pytest.mark.parametrize("weights", [
    {}, {"H8": 1}, {"H8": 2, "H9": float("nan")},
    {"H8": 2, "H9": float("inf")},
])
def test_invalid_band_configuration(weights):
    with pytest.raises(ValueError):
        WFQScheduler(band_weights=weights)
