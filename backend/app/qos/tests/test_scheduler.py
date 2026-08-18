import sys
import unittest
from datetime import datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.classification import PriorityLevel, TrafficClassification
from app.qos import Scheduler


class SchedulerContractTests(unittest.TestCase):
    """Shared behaviour every concrete scheduler must honour."""

    __test__ = False

    def setUp(self):
        self.scheduler = self._make_scheduler()

    def _make_scheduler(self):
        raise NotImplementedError

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

    # -- validation ----------------------------------------------------------

    def test_enqueue_rejects_non_classification(self):
        with self.assertRaises(TypeError):
            self.scheduler.enqueue("not-a-classification")

    def test_enqueue_rejects_none(self):
        with self.assertRaises(TypeError):
            self.scheduler.enqueue(None)

    def test_enqueue_rejects_mismatched_priority(self):
        other = next(
            level
            for level in PriorityLevel
            if level is not self.scheduler.priority
        )
        with self.assertRaises(ValueError):
            self.scheduler.enqueue(self._make_classification(other.value))

    # -- empty behaviour -----------------------------------------------------

    def test_dequeue_on_empty_returns_none(self):
        self.assertIsNone(self.scheduler.dequeue())

    def test_new_scheduler_is_empty(self):
        self.assertTrue(self.scheduler.is_empty())
        self.assertEqual(self.scheduler.size(), 0)

    # -- lifecycle -----------------------------------------------------------

    def test_size_and_is_empty_track_stored_items(self):
        item = self._make_classification(self.scheduler.priority.value)
        self.scheduler.enqueue(item)
        self.assertFalse(self.scheduler.is_empty())
        self.assertEqual(self.scheduler.size(), 1)

        popped = self.scheduler.dequeue()
        self.assertIs(popped, item)
        self.assertTrue(self.scheduler.is_empty())
        self.assertEqual(self.scheduler.size(), 0)

    def test_priority_is_an_assigned_level(self):
        self.assertIsInstance(self.scheduler.priority, PriorityLevel)

    def test_abstract_class_cannot_be_instanced(self):
        with self.assertRaises(TypeError):
            Scheduler()


if __name__ == "__main__":
    unittest.main()