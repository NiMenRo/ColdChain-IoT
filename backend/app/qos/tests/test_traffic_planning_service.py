import sys
import unittest
from datetime import datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.classification import PriorityLevel, TrafficClassification
from app.qos import TrafficPlanningService


class TrafficPlanningServiceTests(unittest.TestCase):

    def setUp(self):
        self.service = TrafficPlanningService()

    def _make_classification(self, priority, criticality=5.0):
        return TrafficClassification(
            id=uuid4(),
            reading_id=uuid4(),
            criticality=criticality,
            priority=priority,
            queue="FIFO",
            classification_time=datetime(2026, 8, 17, 10, 0, 0),
            timestamp=datetime(2026, 8, 17, 9, 59, 30),
        )

    def test_rejects_non_classification(self):
        with self.assertRaises(TypeError):
            self.service.plan("not-a-classification")

    def test_routes_low_priority_to_fifo_queue(self):
        first = self._make_classification(PriorityLevel.LOW.value, criticality=3.0)
        second = self._make_classification(PriorityLevel.LOW.value, criticality=3.5)

        self.service.plan(first)
        self.service.plan(second)

        queue = self.service.get_queue(PriorityLevel.LOW.value)
        self.assertEqual(queue, [first, second])
        self.assertIs(self.service.dequeue(PriorityLevel.LOW.value), first)
        self.assertIs(self.service.dequeue(PriorityLevel.LOW.value), second)

    def test_routes_medium_priority_to_round_robin_queue(self):
        first = self._make_classification(PriorityLevel.MEDIUM.value, criticality=5.0)
        second = self._make_classification(PriorityLevel.MEDIUM.value, criticality=6.0)

        self.service.plan(first)
        self.service.plan(second)

        self.assertEqual(self.service.get_queue(PriorityLevel.MEDIUM.value), [first, second])
        self.assertIs(self.service.dequeue(PriorityLevel.MEDIUM.value), first)
        self.assertIs(self.service.dequeue(PriorityLevel.MEDIUM.value), second)

    def test_routes_high_priority_to_wfq_queue(self):
        first = self._make_classification(PriorityLevel.HIGH.value, criticality=8.0)
        second = self._make_classification(PriorityLevel.HIGH.value, criticality=9.0)

        self.service.plan(first)
        self.service.plan(second)

        self.assertEqual(self.service.get_queue(PriorityLevel.HIGH.value), [first, second])
        self.assertIs(self.service.dequeue(PriorityLevel.HIGH.value), first)
        self.assertIs(self.service.dequeue(PriorityLevel.HIGH.value), second)

    def test_uses_custom_wfq_weight(self):
        service = TrafficPlanningService(wfq_scheduler=__import__('app.qos.application.wfq_scheduler', fromlist=['WFQScheduler']).WFQScheduler(weight=2.5))
        first = self._make_classification(PriorityLevel.HIGH.value, criticality=8.0)
        second = self._make_classification(PriorityLevel.HIGH.value, criticality=9.0)

        service.plan(first)
        service.plan(second)
        self.assertEqual(service.wfq.weight, 2.5)
        self.assertIs(service.dequeue(PriorityLevel.HIGH.value), first)
        self.assertIs(service.dequeue(PriorityLevel.HIGH.value), second)

    def test_plan_keeps_original_classification_reference(self):
        classification = self._make_classification(PriorityLevel.MEDIUM.value, criticality=4.0)
        planned = self.service.plan(classification)

        self.assertIs(planned, classification)
        self.assertIs(self.service.get_queue(PriorityLevel.MEDIUM.value)[0], classification)


if __name__ == "__main__":
    unittest.main()
