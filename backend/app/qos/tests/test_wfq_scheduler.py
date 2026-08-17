import sys
import unittest
from datetime import datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.classification import PriorityLevel, TrafficClassification
from app.qos import WFQScheduler
from app.qos.tests.test_scheduler import SchedulerContractTests


class WFQSchedulerTests(SchedulerContractTests):

    __test__ = True

    def _make_scheduler(self):
        return WFQScheduler()

    def test_priority_is_high(self):
        self.assertIs(self.scheduler.priority, PriorityLevel.HIGH)

    def _make_classification(self, priority):
        return TrafficClassification(
            id=uuid4(),
            reading_id=uuid4(),
            criticality=8.0,
            priority=priority,
            queue="FIFO",
            classification_time=datetime(2026, 8, 17, 10, 0, 0),
            timestamp=datetime(2026, 8, 17, 9, 59, 30),
        )

    # -- neutral weight ------------------------------------------------------

    def test_default_weight_is_neutral(self):
        self.assertEqual(self.scheduler.weight, 1.0)

    def test_services_high_flow_in_arrival_order_with_default_weight(self):
        first = self._make_classification(PriorityLevel.HIGH.value)
        second = self._make_classification(PriorityLevel.HIGH.value)
        third = self._make_classification(PriorityLevel.HIGH.value)

        self.scheduler.enqueue(first)
        self.scheduler.enqueue(second)
        self.scheduler.enqueue(third)

        self.assertIs(self.scheduler.dequeue(), first)
        self.assertIs(self.scheduler.dequeue(), second)
        self.assertIs(self.scheduler.dequeue(), third)

    # -- virtual time accounting --------------------------------------------

    def test_virtual_time_advances_by_finish_of_served_entry(self):
        first = self._make_classification(PriorityLevel.HIGH.value)
        second = self._make_classification(PriorityLevel.HIGH.value)

        self.scheduler.enqueue(first)
        self.scheduler.enqueue(second)
        self.assertEqual(self.scheduler.virtual_time, 0.0)

        self.scheduler.dequeue()
        self.assertEqual(self.scheduler.virtual_time, 1.0)
        self.scheduler.dequeue()
        self.assertEqual(self.scheduler.virtual_time, 2.0)

    def test_custom_weight_scales_finish_times(self):
        scheduler = WFQScheduler(weight=2.5)
        first = self._make_classification(PriorityLevel.HIGH.value)
        second = self._make_classification(PriorityLevel.HIGH.value)

        scheduler.enqueue(first)
        scheduler.enqueue(second)
        self.assertEqual(scheduler.weight, 2.5)

        scheduler.dequeue()
        self.assertEqual(scheduler.virtual_time, 2.5)
        scheduler.dequeue()
        self.assertEqual(scheduler.virtual_time, 5.0)

    # -- weight validation ---------------------------------------------------

    def test_weight_rejects_zero(self):
        with self.assertRaises(ValueError):
            WFQScheduler(weight=0)

    def test_weight_rejects_negative(self):
        with self.assertRaises(ValueError):
            WFQScheduler(weight=-1)

    def test_weight_rejects_non_numeric(self):
        with self.assertRaises(TypeError):
            WFQScheduler(weight="heavy")

    def test_weight_rejects_boolean(self):
        with self.assertRaises(TypeError):
            WFQScheduler(weight=True)


if __name__ == "__main__":
    unittest.main()