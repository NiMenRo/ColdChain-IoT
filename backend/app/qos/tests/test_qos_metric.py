import sys
import unittest
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.qos.domain import QoSMetric


class QoSMetricTests(unittest.TestCase):

    def _make_valid_kwargs(self):
        return {
            "id": uuid4(),
            "classification_id": uuid4(),
            "latency": 12.5,
            "packet_loss": 0.5,
            "throughput": 1024.0,
            "pdr": 99.2,
            "jitter": 3.1,
            "timestamp": datetime(2026, 8, 16, 10, 0, 0),
        }

    def test_creates_with_valid_fields(self):
        metric = QoSMetric(**self._make_valid_kwargs())
        self.assertIsInstance(metric.id, UUID)
        self.assertIsInstance(metric.classification_id, UUID)
        self.assertEqual(metric.latency, 12.5)
        self.assertEqual(metric.packet_loss, 0.5)
        self.assertEqual(metric.throughput, 1024.0)
        self.assertEqual(metric.pdr, 99.2)
        self.assertEqual(metric.jitter, 3.1)
        self.assertIsInstance(metric.timestamp, datetime)

    def test_rejects_non_uuid_id(self):
        kwargs = self._make_valid_kwargs()
        kwargs["id"] = "not-a-uuid"
        with self.assertRaises(TypeError):
            QoSMetric(**kwargs)

    def test_rejects_non_uuid_classification_id(self):
        kwargs = self._make_valid_kwargs()
        kwargs["classification_id"] = 123
        with self.assertRaises(TypeError):
            QoSMetric(**kwargs)

    def test_rejects_non_numeric_latency(self):
        kwargs = self._make_valid_kwargs()
        kwargs["latency"] = "fast"
        with self.assertRaises(TypeError):
            QoSMetric(**kwargs)

    def test_rejects_boolean_latency(self):
        kwargs = self._make_valid_kwargs()
        kwargs["latency"] = True
        with self.assertRaises(TypeError):
            QoSMetric(**kwargs)

    def test_rejects_non_numeric_packet_loss(self):
        kwargs = self._make_valid_kwargs()
        kwargs["packet_loss"] = None
        with self.assertRaises(TypeError):
            QoSMetric(**kwargs)

    def test_rejects_boolean_packet_loss(self):
        kwargs = self._make_valid_kwargs()
        kwargs["packet_loss"] = False
        with self.assertRaises(TypeError):
            QoSMetric(**kwargs)

    def test_rejects_non_numeric_throughput(self):
        kwargs = self._make_valid_kwargs()
        kwargs["throughput"] = "high"
        with self.assertRaises(TypeError):
            QoSMetric(**kwargs)

    def test_rejects_boolean_throughput(self):
        kwargs = self._make_valid_kwargs()
        kwargs["throughput"] = True
        with self.assertRaises(TypeError):
            QoSMetric(**kwargs)

    def test_rejects_non_numeric_pdr(self):
        kwargs = self._make_valid_kwargs()
        kwargs["pdr"] = []
        with self.assertRaises(TypeError):
            QoSMetric(**kwargs)

    def test_rejects_boolean_pdr(self):
        kwargs = self._make_valid_kwargs()
        kwargs["pdr"] = False
        with self.assertRaises(TypeError):
            QoSMetric(**kwargs)

    def test_rejects_non_numeric_jitter(self):
        kwargs = self._make_valid_kwargs()
        kwargs["jitter"] = "high"
        with self.assertRaises(TypeError):
            QoSMetric(**kwargs)

    def test_rejects_boolean_jitter(self):
        kwargs = self._make_valid_kwargs()
        kwargs["jitter"] = True
        with self.assertRaises(TypeError):
            QoSMetric(**kwargs)

    def test_rejects_non_datetime_timestamp(self):
        kwargs = self._make_valid_kwargs()
        kwargs["timestamp"] = "2026-08-16T10:00:00"
        with self.assertRaises(TypeError):
            QoSMetric(**kwargs)

    def test_accepts_integer_values_for_float_metrics(self):
        kwargs = self._make_valid_kwargs()
        kwargs["latency"] = 10
        kwargs["packet_loss"] = 1
        kwargs["throughput"] = 2048
        kwargs["pdr"] = 100
        kwargs["jitter"] = 2
        metric = QoSMetric(**kwargs)
        self.assertEqual(metric.latency, 10)
        self.assertEqual(metric.packet_loss, 1)
        self.assertEqual(metric.throughput, 2048)
        self.assertEqual(metric.pdr, 100)
        self.assertEqual(metric.jitter, 2)


if __name__ == "__main__":
    unittest.main()