import sys
import unittest
from datetime import datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.classification import PriorityLevel, TrafficClassification
from app.qos import RoundRobinScheduler
from app.qos.tests.test_scheduler import SchedulerContractTests


class RoundRobinSchedulerTests(SchedulerContractTests):

    __test__ = True

    def _make_scheduler(self):
        return RoundRobinScheduler()

    def test_priority_is_medium(self):
        self.assertIs(self.scheduler.priority, PriorityLevel.MEDIUM)

    def _make_classification(self, priority):
        return TrafficClassification(
            id=uuid4(),
            reading_id=uuid4(),
            criticality=5.0,
            priority=priority,
            queue="FIFO",
            classification_time=datetime(2026, 8, 17, 10, 0, 0),
            timestamp=datetime(2026, 8, 17, 9, 59, 30),
        )

    # -- legacy demonstration compatibility ---------------------------------

    def test_legacy_classifications_keep_arrival_order_without_default_slot(self):
        first = self._make_classification(PriorityLevel.MEDIUM.value)
        second = self._make_classification(PriorityLevel.MEDIUM.value)
        third = self._make_classification(PriorityLevel.MEDIUM.value)

        self.scheduler.enqueue(first)
        self.scheduler.enqueue(second)
        self.scheduler.enqueue(third)

        self.assertIs(self.scheduler.dequeue(), first)
        self.assertIs(self.scheduler.dequeue(), second)
        self.assertIs(self.scheduler.dequeue(), third)

    def test_draining_all_legacy_flows_counts_a_round(self):
        first = self._make_classification(PriorityLevel.MEDIUM.value)
        second = self._make_classification(PriorityLevel.MEDIUM.value)

        self.assertEqual(self.scheduler.rounds, 0)
        self.scheduler.enqueue(first)
        self.scheduler.enqueue(second)

        self.scheduler.dequeue()
        self.assertEqual(self.scheduler.rounds, 0)
        self.scheduler.dequeue()
        self.assertEqual(self.scheduler.rounds, 1)

    def test_empty_dequeue_does_not_advance_rounds(self):
        first = self._make_classification(PriorityLevel.MEDIUM.value)
        self.scheduler.enqueue(first)

        self.scheduler.dequeue()
        self.assertEqual(self.scheduler.rounds, 1)
        self.assertIsNone(self.scheduler.dequeue())
        self.assertEqual(self.scheduler.rounds, 1)

    def test_no_default_slot_exists_before_admission(self):
        self.assertEqual(self.scheduler.slot_names, [])


if __name__ == "__main__":
    unittest.main()
