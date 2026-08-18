import sys
import unittest
from datetime import datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.classification import PriorityLevel, TrafficClassification
from app.qos import TrafficQueueOrganizer


class TrafficQueueOrganizerTests(unittest.TestCase):

    def setUp(self):
        self.organizer = TrafficQueueOrganizer()

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

    # -- routing -------------------------------------------------------------

    def test_high_priority_goes_to_high_queue(self):
        self.organizer.enqueue(self._make_classification(PriorityLevel.HIGH.value))
        self.assertEqual(self.organizer.queue_length(PriorityLevel.HIGH.value), 1)
        self.assertEqual(self.organizer.queue_length(PriorityLevel.MEDIUM.value), 0)
        self.assertEqual(self.organizer.queue_length(PriorityLevel.LOW.value), 0)
        self.assertEqual(
            self.organizer.get_queue(PriorityLevel.HIGH.value)[0].priority,
            "high",
        )

    def test_medium_priority_goes_to_medium_queue(self):
        self.organizer.enqueue(self._make_classification(PriorityLevel.MEDIUM.value))
        self.assertEqual(self.organizer.queue_length(PriorityLevel.MEDIUM.value), 1)
        self.assertEqual(self.organizer.queue_length(PriorityLevel.HIGH.value), 0)
        self.assertEqual(self.organizer.queue_length(PriorityLevel.LOW.value), 0)

    def test_low_priority_goes_to_low_queue(self):
        self.organizer.enqueue(self._make_classification(PriorityLevel.LOW.value))
        self.assertEqual(self.organizer.queue_length(PriorityLevel.LOW.value), 1)
        self.assertEqual(self.organizer.queue_length(PriorityLevel.HIGH.value), 0)
        self.assertEqual(self.organizer.queue_length(PriorityLevel.MEDIUM.value), 0)

    def test_priorities_do_not_mix_between_queues(self):
        self.organizer.enqueue(self._make_classification(PriorityLevel.HIGH.value))
        self.organizer.enqueue(self._make_classification(PriorityLevel.MEDIUM.value))
        self.organizer.enqueue(self._make_classification(PriorityLevel.LOW.value))

        high_items = self.organizer.get_queue(PriorityLevel.HIGH.value)
        medium_items = self.organizer.get_queue(PriorityLevel.MEDIUM.value)
        low_items = self.organizer.get_queue(PriorityLevel.LOW.value)

        self.assertEqual(len(high_items), 1)
        self.assertEqual(len(medium_items), 1)
        self.assertEqual(len(low_items), 1)
        self.assertEqual(high_items[0].priority, "high")
        self.assertEqual(medium_items[0].priority, "medium")
        self.assertEqual(low_items[0].priority, "low")

    # -- ordering ------------------------------------------------------------

    def test_multiple_classifications_preserve_arrival_order(self):
        first = self._make_classification(PriorityLevel.LOW.value)
        second = self._make_classification(PriorityLevel.LOW.value)
        third = self._make_classification(PriorityLevel.LOW.value)

        self.organizer.enqueue(first)
        self.organizer.enqueue(second)
        self.organizer.enqueue(third)

        items = self.organizer.get_queue(PriorityLevel.LOW.value)
        self.assertEqual([i.id for i in items], [first.id, second.id, third.id])

    # -- state ---------------------------------------------------------------

    def test_queue_length_returns_size(self):
        self.assertEqual(self.organizer.queue_length(PriorityLevel.HIGH.value), 0)
        self.organizer.enqueue(self._make_classification(PriorityLevel.HIGH.value))
        self.organizer.enqueue(self._make_classification(PriorityLevel.HIGH.value))
        self.organizer.enqueue(self._make_classification(PriorityLevel.HIGH.value))
        self.assertEqual(self.organizer.queue_length(PriorityLevel.HIGH.value), 3)

    def test_total_count_returns_total_across_queues(self):
        self.assertEqual(self.organizer.total_count(), 0)
        self.organizer.enqueue(self._make_classification(PriorityLevel.HIGH.value))
        self.organizer.enqueue(self._make_classification(PriorityLevel.HIGH.value))
        self.organizer.enqueue(self._make_classification(PriorityLevel.MEDIUM.value))
        self.organizer.enqueue(self._make_classification(PriorityLevel.LOW.value))
        self.assertEqual(self.organizer.total_count(), 4)

    def test_is_empty_works(self):
        self.assertTrue(self.organizer.is_empty(PriorityLevel.MEDIUM.value))
        self.organizer.enqueue(self._make_classification(PriorityLevel.MEDIUM.value))
        self.assertFalse(self.organizer.is_empty(PriorityLevel.MEDIUM.value))

    def test_pop_preserves_fifo_order(self):
        first = self._make_classification(PriorityLevel.HIGH.value)
        second = self._make_classification(PriorityLevel.HIGH.value)

        self.organizer.enqueue(first)
        self.organizer.enqueue(second)

        self.assertIs(self.organizer.pop(PriorityLevel.HIGH.value), first)
        self.assertIs(self.organizer.pop(PriorityLevel.HIGH.value), second)
        self.assertTrue(self.organizer.is_empty(PriorityLevel.HIGH.value))

    def test_peek_does_not_remove_element(self):
        first = self._make_classification(PriorityLevel.MEDIUM.value)
        self.organizer.enqueue(first)

        self.assertIs(self.organizer.peek(PriorityLevel.MEDIUM.value), first)
        self.assertEqual(self.organizer.queue_length(PriorityLevel.MEDIUM.value), 1)

    def test_pop_on_empty_queue_returns_none(self):
        self.assertIsNone(self.organizer.pop(PriorityLevel.LOW.value))

    def test_get_queue_does_not_modify_queue(self):
        self.organizer.enqueue(self._make_classification(PriorityLevel.HIGH.value))
        snapshot = self.organizer.get_queue(PriorityLevel.HIGH.value)
        snapshot.pop()
        self.assertEqual(self.organizer.queue_length(PriorityLevel.HIGH.value), 1)

    # -- validation ----------------------------------------------------------

    def test_enqueue_rejects_non_classification(self):
        with self.assertRaises(TypeError):
            self.organizer.enqueue("not-a-classification")

    def test_enqueue_rejects_none(self):
        with self.assertRaises(TypeError):
            self.organizer.enqueue(None)

    def test_query_unknown_priority_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.organizer.get_queue("urgent")

    def test_all_priority_operations_reject_unknown_priority(self):
        for operation in (
            lambda: self.organizer.get_queue("urgent"),
            lambda: self.organizer.queue_length("urgent"),
            lambda: self.organizer.is_empty("urgent"),
            lambda: self.organizer.pop("urgent"),
            lambda: self.organizer.peek("urgent"),
        ):
            with self.assertRaises(ValueError):
                operation()


if __name__ == "__main__":
    unittest.main()