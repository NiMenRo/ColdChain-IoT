from app.qos import QoSDispatcher, TrafficPlanningService
from app.qos.tests.test_fifo_work_items import _item


def test_dispatcher_applies_exact_four_two_one_cycle_under_saturation():
    planner = TrafficPlanningService()
    items = []
    for priority, count in (("high", 8), ("medium", 4), ("low", 2)):
        for sequence in range(count):
            item = _item(sequence, priority)
            items.append(item)
            planner.plan(item)
    dispatcher = QoSDispatcher(planner)
    selected = [dispatcher.select_next() for _ in items]
    assert [item.priority for item in selected] == (
        ["high"] * 4 + ["medium"] * 2 + ["low"]
    ) * 2


def test_dispatcher_skips_empty_classes_and_resets_after_empty_system():
    planner = TrafficPlanningService()
    low = _item(1, "low")
    planner.plan(low)
    dispatcher = QoSDispatcher(planner)
    assert dispatcher.select_next() is low
    assert dispatcher.select_next() is None
    high = _item(2, "high")
    planner.plan(high)
    assert dispatcher.select_next() is high
