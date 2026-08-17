import sys
import unittest
from datetime import datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.classification import PriorityLevel, TrafficClassification
from app.qos import FIFOScheduler
from app.qos.tests.test_scheduler import SchedulerContractTests


class FIFOSchedulerTests(SchedulerContractTests):

    __test__ = True

    def _make_scheduler(self):
        return FIFOScheduler()

    def test_priority_is_low(self):
        self.assertIs(self.scheduler.priority, PriorityLevel.LOW)

    def _make_classification(self, priority):
        return TrafficClassification(
            id=uuid4(),
            reading_id=uuid4(),
            criticality=2.0,
            priority=priority,
            queue="FIFO",
            classification_time=datetime(2026, 8, 17, 10, 0, 0),
            timestamp=datetime(2026, 8, 17, 9, 59, 30),
        )

    # -- ordering ------------------------------------------------------------

    def test_dequeue_preserves_arrival_order(self):
        first = self._make_classification(PriorityLevel.LOW.value)
        second = self._make_classification(PriorityLevel.LOW.value)
        third = self._make_classification(PriorityLevel.LOW.value)

        self.scheduler.enqueue(first)
        self.scheduler.enqueue(second)
        self.scheduler.enqueue(third)

        self.assertIs(self.scheduler.dequeue(), first)
        self.assertIs(self.scheduler.dequeue(), second)
        self.assertIs(self.scheduler.dequeue(), third)
        self.assertIsNone(self.scheduler.dequeue())


if __name__ == "__main__":
    unittest.main()