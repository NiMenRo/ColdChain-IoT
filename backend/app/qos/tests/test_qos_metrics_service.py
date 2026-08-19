import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.qos.application.qos_metrics_service import MessageDeliveryRecord, QoSMetricsService


class QoSMetricsServiceTests(unittest.TestCase):

    def setUp(self):
        self.service = QoSMetricsService()

    def test_calculates_latency(self):
        sent_at = datetime(2026, 8, 17, 10, 0, 0)
        received_at = sent_at + timedelta(seconds=2.5)
        self.assertEqual(self.service.calculate_latency(sent_at, received_at), 2.5)

    def test_calculates_jitter_from_latencies(self):
        latencies = [1.0, 2.0, 1.5]
        self.assertEqual(self.service.calculate_jitter(latencies), 0.75)

    def test_calculates_throughput(self):
        records = [
            MessageDeliveryRecord(
                message_id=uuid4(),
                sent_at=datetime(2026, 8, 17, 10, 0, 0),
                received_at=datetime(2026, 8, 17, 10, 0, 2),
                size_bytes=200.0,
                delivered=True,
                criticality=8.0,
                priority="high",
            ),
            MessageDeliveryRecord(
                message_id=uuid4(),
                sent_at=datetime(2026, 8, 17, 10, 0, 2),
                received_at=datetime(2026, 8, 17, 10, 0, 4),
                size_bytes=400.0,
                delivered=True,
                criticality=6.0,
                priority="medium",
            ),
        ]
        self.assertEqual(self.service.calculate_throughput(records, interval_seconds=4.0), 150.0)

    def test_calculates_pdr(self):
        self.assertEqual(self.service.calculate_pdr(10, 8), 80.0)

    def test_calculates_packet_loss(self):
        self.assertEqual(self.service.calculate_packet_loss(10, 8), 20.0)

    def test_summarizes_by_priority(self):
        records = [
            MessageDeliveryRecord(
                message_id=uuid4(),
                sent_at=datetime(2026, 8, 17, 10, 0, 0),
                received_at=datetime(2026, 8, 17, 10, 0, 1),
                size_bytes=128.0,
                delivered=True,
                criticality=8.0,
                priority="high",
            ),
            MessageDeliveryRecord(
                message_id=uuid4(),
                sent_at=datetime(2026, 8, 17, 10, 0, 0),
                received_at=datetime(2026, 8, 17, 10, 0, 2),
                size_bytes=64.0,
                delivered=True,
                criticality=3.0,
                priority="low",
            ),
        ]
        summary = self.service.summarize_by_priority(records)
        self.assertIn("high", summary)
        self.assertIn("low", summary)
        self.assertIn("pdr", summary["high"])


if __name__ == "__main__":
    unittest.main()
