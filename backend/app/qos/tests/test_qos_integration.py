import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.classification.domain import TrafficClassification
from app.qos import QoSMetricsService, TrafficPlanningService
from app.qos.api import router
from app.qos.application.qos_metrics_service import MessageDeliveryRecord


class QoSIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.service = TrafficPlanningService()
        self.metrics = QoSMetricsService()

        self.app = FastAPI()
        self.app.include_router(router)
        self.app.state.qos_service = TrafficPlanningService()
        self.app.state.qos_metrics_service = QoSMetricsService()
        self.app.state.qos_records = []
        self.client = TestClient(self.app)

    def _make_classification(self, priority: str, criticality: float, sent_at: datetime):
        return TrafficClassification(
            id=uuid4(),
            reading_id=uuid4(),
            criticality=criticality,
            priority=priority,
            queue={
                "low": "FIFO",
                "medium": "Round Robin",
                "high": "WFQ",
            }[priority],
            classification_time=sent_at + timedelta(seconds=1),
            timestamp=sent_at,
        )

    def test_qos_planning_routes_each_priority_to_its_queue(self):
        low = self._make_classification("low", 3.2, datetime(2026, 8, 17, 10, 0, 0))
        medium = self._make_classification("medium", 5.5, datetime(2026, 8, 17, 10, 0, 2))
        high = self._make_classification("high", 8.5, datetime(2026, 8, 17, 10, 0, 4))

        self.service.plan(low)
        self.service.plan(medium)
        self.service.plan(high)

        self.assertEqual(self.service.get_queue("low"), [low])
        self.assertEqual(self.service.get_queue("medium"), [medium])
        self.assertEqual(self.service.get_queue("high"), [high])

        self.assertIs(self.service.dequeue("low"), low)
        self.assertIs(self.service.dequeue("medium"), medium)
        self.assertIs(self.service.dequeue("high"), high)

    def test_qos_metrics_are_calculated_for_simulated_traffic(self):
        records = [
            MessageDeliveryRecord(
                message_id="msg-001",
                sent_at=datetime(2026, 8, 17, 10, 0, 0),
                received_at=datetime(2026, 8, 17, 10, 0, 1),
                size_bytes=128.0,
                delivered=True,
                criticality=8.0,
                priority="high",
            ),
            MessageDeliveryRecord(
                message_id="msg-002",
                sent_at=datetime(2026, 8, 17, 10, 0, 2),
                received_at=datetime(2026, 8, 17, 10, 0, 4),
                size_bytes=256.0,
                delivered=True,
                criticality=5.0,
                priority="medium",
            ),
            MessageDeliveryRecord(
                message_id="msg-003",
                sent_at=datetime(2026, 8, 17, 10, 0, 5),
                received_at=datetime(2026, 8, 17, 10, 0, 7),
                size_bytes=64.0,
                delivered=False,
                criticality=3.0,
                priority="low",
            ),
        ]

        summary = self.metrics.summarize(records)

        self.assertIn("latency", summary)
        self.assertIn("jitter", summary)
        self.assertIn("throughput", summary)
        self.assertIn("pdr", summary)
        self.assertIn("packet_loss", summary)
        self.assertAlmostEqual(summary["pdr"], 66.66666666666666, places=4)
        self.assertAlmostEqual(summary["packet_loss"], 33.33333333333333, places=4)

    def test_qos_api_integrates_planning_and_metrics(self):
        low_payload = {
            "id": "7e5c7746-c4aa-4a8c-8db3-ffbbf4a0d1cf",
            "reading_id": "5a3d04f0-6ed0-41cd-a102-b0d6168439c7",
            "criticality": 3.2,
            "priority": "low",
            "queue": "FIFO",
            "classification_time": "2026-08-18T11:00:01",
            "timestamp": "2026-08-18T11:00:00",
        }
        medium_payload = {
            "id": "c8b5cc02-7cc8-4fb9-ae86-e0bc323d775a",
            "reading_id": "c33d4b10-471d-4324-8d04-4d0d925b7d54",
            "criticality": 5.5,
            "priority": "medium",
            "queue": "Round Robin",
            "classification_time": "2026-08-18T11:00:03",
            "timestamp": "2026-08-18T11:00:02",
        }
        high_payload = {
            "id": "d3d6c96d-0d88-4e9f-9ec2-c3c3fcf63c7a",
            "reading_id": "0f1d53d5-99d7-4c8b-aa97-7f1d7d4b1d28",
            "criticality": 8.5,
            "priority": "high",
            "queue": "WFQ",
            "classification_time": "2026-08-18T11:00:05",
            "timestamp": "2026-08-18T11:00:04",
        }

        for payload in (low_payload, medium_payload, high_payload):
            response = self.client.post("/qos/plan", json=payload)
            self.assertEqual(response.status_code, 202)

        queue_response = self.client.get("/qos/queues")
        self.assertEqual(queue_response.status_code, 200)
        queues = queue_response.json()["queues"]
        self.assertIn("low", queues)
        self.assertIn("medium", queues)
        self.assertIn("high", queues)

        metrics_response = self.client.get("/qos/metrics")
        self.assertEqual(metrics_response.status_code, 200)
        summary = metrics_response.json()["summary"]
        self.assertIn("latency", summary)
        self.assertIn("throughput", summary)
        self.assertIn("pdr", summary)

    def test_qos_api_rejects_invalid_priority(self):
        payload = {
            "id": "7d8a5d7a-0f25-415f-a203-20f56bc4f54a",
            "reading_id": "63fcb5ed-8e62-4b2a-9a54-114a5094517a",
            "criticality": 6.0,
            "priority": "urgent",
            "queue": "Round Robin",
            "classification_time": "2026-08-18T11:04:00",
            "timestamp": "2026-08-18T11:03:00",
        }
        response = self.client.post("/qos/plan", json=payload)
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
