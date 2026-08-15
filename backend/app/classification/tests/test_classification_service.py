import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.acquisition.normalizer import NormalizedReading
from app.classification.application.classification_service import ClassificationService
from app.classification.application.criticality_calculator import CriticalityCalculator
from app.classification.application.priority_assigner import PriorityAssigner
from app.classification.domain import TrafficClassification


class ClassificationServiceTests(unittest.TestCase):

    def setUp(self):
        self.calculator = CriticalityCalculator()
        self.assigner = PriorityAssigner()
        self.service = ClassificationService(
            calculator=self.calculator,
            assigner=self.assigner,
        )

    def _make_reading(self, timestamp="2026-08-13T10:00:00"):
        return NormalizedReading(
            device_code="CAVA-001",
            device_type="cold_room",
            sensor_name="temperature",
            value=4.5,
            timestamp=timestamp,
            raw_value=4.5,
        )

    # -- classification flow tests -------------------------------------------

    def test_all_high_returns_high_priority_wfq(self):
        tc = self.service.classify(self._make_reading(), impact=3, urgency=3, risk=3)
        self.assertEqual(tc.criticality, 9)
        self.assertEqual(tc.priority, "high")
        self.assertEqual(tc.queue, "WFQ")

    def test_all_medium_returns_medium_priority_round_robin(self):
        tc = self.service.classify(self._make_reading(), impact=2, urgency=2, risk=2)
        self.assertEqual(tc.criticality, 6)
        self.assertEqual(tc.priority, "medium")
        self.assertEqual(tc.queue, "Round Robin")

    def test_all_low_returns_low_priority_fifo(self):
        tc = self.service.classify(self._make_reading(), impact=1, urgency=1, risk=1)
        self.assertEqual(tc.criticality, 3)
        self.assertEqual(tc.priority, "low")
        self.assertEqual(tc.queue, "FIFO")

    def test_boundary_high_returns_wfq(self):
        tc = self.service.classify(self._make_reading(), impact=2, urgency=3, risk=2)
        self.assertEqual(tc.criticality, 7)
        self.assertEqual(tc.priority, "high")
        self.assertEqual(tc.queue, "WFQ")

    def test_boundary_medium_returns_round_robin(self):
        tc = self.service.classify(self._make_reading(), impact=1, urgency=1, risk=2)
        self.assertEqual(tc.criticality, 4)
        self.assertEqual(tc.priority, "medium")
        self.assertEqual(tc.queue, "Round Robin")

    # -- entity field tests --------------------------------------------------

    def test_reading_id_is_uuid(self):
        from uuid import UUID
        tc = self.service.classify(self._make_reading(), impact=1, urgency=1, risk=1)
        self.assertIsInstance(tc.reading_id, UUID)

    def test_id_is_uuid(self):
        from uuid import UUID
        tc = self.service.classify(self._make_reading(), impact=1, urgency=1, risk=1)
        self.assertIsInstance(tc.id, UUID)

    def test_classification_time_is_datetime(self):
        tc = self.service.classify(self._make_reading(), impact=1, urgency=1, risk=1)
        self.assertIsInstance(tc.classification_time, datetime)

    def test_timestamp_from_reading(self):
        reading = self._make_reading(timestamp="2026-07-20T21:30:15")
        tc = self.service.classify(reading, impact=1, urgency=1, risk=1)
        self.assertEqual(tc.timestamp, datetime(2026, 7, 20, 21, 30, 15))

    # -- validation tests ----------------------------------------------------

    def test_rejects_none_reading(self):
        with self.assertRaises(TypeError):
            self.service.classify(None, impact=1, urgency=1, risk=1)

    def test_rejects_invalid_impact(self):
        with self.assertRaises(TypeError):
            self.service.classify(self._make_reading(), impact="high", urgency=1, risk=1)

    def test_rejects_invalid_urgency(self):
        with self.assertRaises(TypeError):
            self.service.classify(self._make_reading(), impact=1, urgency=1.5, risk=1)

    def test_rejects_invalid_risk(self):
        with self.assertRaises(ValueError):
            self.service.classify(self._make_reading(), impact=1, urgency=1, risk=4)


if __name__ == "__main__":
    unittest.main()
