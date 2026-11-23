from collections import Counter

import pytest

from app.classification.application.criticality_calculator import CriticalityCalculator
from app.classification.application.priority_assigner import PriorityAssigner
from app.qos.application.wfq_scheduler import WFQScheduler
from app.qos.tests.test_wfq_work_items import _item


@pytest.mark.parametrize("score,expected", [
    (3, "low"), (4, "low"), (5, "medium"), (6, "medium"),
    (7, "medium"), (8, "high"), (9, "high"),
])
def test_document_priority_boundaries(score, expected):
    assert PriorityAssigner().assign(score).value == expected
    assert CriticalityCalculator().classify(score).value == expected


def test_wfq_document_weights_and_saturated_share():
    scheduler = WFQScheduler()
    assert scheduler.band_weights == {"H8": 2, "H9": 3}
    for i in range(100):
        scheduler.enqueue(_item("a", 2 * i, 8))
        scheduler.enqueue(_item("b", 2 * i + 1, 9))
    assert Counter(scheduler.band_for(scheduler.dequeue()) for _ in range(100)) == {
        "H8": 40, "H9": 60,
    }
    with pytest.raises(ValueError):
        scheduler.enqueue(_item("c", 201, 7))
