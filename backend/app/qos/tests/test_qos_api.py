import sys
import unittest
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.qos.api import router
from app.qos.application.qos_metrics_service import QoSMetricsService
from app.qos.application.traffic_planning_service import TrafficPlanningService


class QoSApiTests(unittest.TestCase):

    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.state.qos_service = TrafficPlanningService()
        self.app.state.qos_metrics_service = QoSMetricsService()
        self.app.state.qos_records = []
        self.client = TestClient(self.app)

    def test_plan_endpoint_accepts_valid_classification(self):
        payload = {
            "id": "7e5c7746-c4aa-4a8c-8db3-ffbbf4a0d1cf",
            "reading_id": "5a3d04f0-6ed0-41cd-a102-b0d6168439c7",
            "criticality": 8.5,
            "priority": "high",
            "queue": "WFQ",
            "classification_time": "2026-08-18T11:00:00",
            "timestamp": "2026-08-18T10:59:00",
        }
        response = self.client.post("/qos/plan", json=payload)
        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["priority"], "high")
        self.assertEqual(body["planned_queue"], "WFQ")

    def test_queue_endpoint_lists_current_plan_entries(self):
        payload = {
            "id": "c8b5cc02-7cc8-4fb9-ae86-e0bc323d775a",
            "reading_id": "c33d4b10-471d-4324-8d04-4d0d925b7d54",
            "criticality": 5.5,
            "priority": "medium",
            "queue": "Round Robin",
            "classification_time": "2026-08-18T11:02:00",
            "timestamp": "2026-08-18T11:01:00",
        }
        self.client.post("/qos/plan", json=payload)
        response = self.client.get("/qos/queues")
        self.assertEqual(response.status_code, 200)
        self.assertIn("medium", response.json()["queues"])

    def test_metrics_endpoint_returns_summary(self):
        payload = {
            "id": "53b9831e-00af-454f-86cd-0d0ee47010e9",
            "reading_id": "eefbe4d0-8d8d-43cf-aad9-c229d5dce6db",
            "criticality": 7.0,
            "priority": "high",
            "queue": "WFQ",
            "classification_time": "2026-08-18T11:03:00",
            "timestamp": "2026-08-18T11:02:00",
        }
        self.client.post("/qos/plan", json=payload)
        response = self.client.get("/qos/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json()["count"], 0)
        self.assertIn("summary", response.json())

    def test_invalid_priority_is_rejected(self):
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
