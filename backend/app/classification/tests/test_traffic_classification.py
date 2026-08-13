import sys
import unittest
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.classification.domain import TrafficClassification


class TrafficClassificationTests(unittest.TestCase):

    def _make_valid_kwargs(self):
        return {
            "id": uuid4(),
            "reading_id": uuid4(),
            "criticality": 5.0,
            "priority": "medium",
            "queue": "FIFO",
            "classification_time": datetime(2026, 8, 12, 10, 0, 0),
            "timestamp": datetime(2026, 8, 12, 9, 59, 30),
        }

    def test_creates_with_valid_fields(self):
        tc = TrafficClassification(**self._make_valid_kwargs())
        self.assertIsInstance(tc.id, UUID)
        self.assertIsInstance(tc.reading_id, UUID)
        self.assertEqual(tc.criticality, 5.0)
        self.assertEqual(tc.priority, "medium")
        self.assertEqual(tc.queue, "FIFO")
        self.assertIsInstance(tc.classification_time, datetime)
        self.assertIsInstance(tc.timestamp, datetime)

    def test_rejects_non_uuid_id(self):
        kwargs = self._make_valid_kwargs()
        kwargs["id"] = "not-a-uuid"
        with self.assertRaises(TypeError):
            TrafficClassification(**kwargs)

    def test_rejects_non_uuid_reading_id(self):
        kwargs = self._make_valid_kwargs()
        kwargs["reading_id"] = 123
        with self.assertRaises(TypeError):
            TrafficClassification(**kwargs)

    def test_rejects_non_numeric_criticality(self):
        kwargs = self._make_valid_kwargs()
        kwargs["criticality"] = "high"
        with self.assertRaises(TypeError):
            TrafficClassification(**kwargs)

    def test_rejects_boolean_criticality(self):
        kwargs = self._make_valid_kwargs()
        kwargs["criticality"] = True
        with self.assertRaises(TypeError):
            TrafficClassification(**kwargs)

    def test_rejects_empty_priority(self):
        kwargs = self._make_valid_kwargs()
        kwargs["priority"] = ""
        with self.assertRaises(ValueError):
            TrafficClassification(**kwargs)

    def test_rejects_whitespace_only_priority(self):
        kwargs = self._make_valid_kwargs()
        kwargs["priority"] = "   "
        with self.assertRaises(ValueError):
            TrafficClassification(**kwargs)

    def test_rejects_non_string_priority(self):
        kwargs = self._make_valid_kwargs()
        kwargs["priority"] = 1
        with self.assertRaises(ValueError):
            TrafficClassification(**kwargs)

    def test_rejects_empty_queue(self):
        kwargs = self._make_valid_kwargs()
        kwargs["queue"] = ""
        with self.assertRaises(ValueError):
            TrafficClassification(**kwargs)

    def test_rejects_non_string_queue(self):
        kwargs = self._make_valid_kwargs()
        kwargs["queue"] = None
        with self.assertRaises(ValueError):
            TrafficClassification(**kwargs)

    def test_rejects_non_datetime_classification_time(self):
        kwargs = self._make_valid_kwargs()
        kwargs["classification_time"] = "2026-08-12T10:00:00"
        with self.assertRaises(TypeError):
            TrafficClassification(**kwargs)

    def test_rejects_non_datetime_timestamp(self):
        kwargs = self._make_valid_kwargs()
        kwargs["timestamp"] = "2026-08-12T10:00:00"
        with self.assertRaises(TypeError):
            TrafficClassification(**kwargs)

    def test_accepts_integer_criticality(self):
        kwargs = self._make_valid_kwargs()
        kwargs["criticality"] = 7
        tc = TrafficClassification(**kwargs)
        self.assertEqual(tc.criticality, 7)

if __name__ == "__main__":
    unittest.main()
