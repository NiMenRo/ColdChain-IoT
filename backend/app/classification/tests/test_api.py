import sys
import unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure repo root is on sys.path when running tests
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.classification.api import router


class ClassificationAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    def test_classify_endpoint_accepts_valid_request(self):
        payload = {
            "reading": {
                "device_code": "CAVA-001",
                "device_type": "cold_room",
                "sensor_name": "temperature",
                "value": 4.5,
                "timestamp": "2026-08-04T10:00:00",
                "raw_value": 4.5,
            },
            "impact": 2,
            "urgency": 2,
            "risk": 2,
        }
        resp = self.client.post("/classification/classify", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("id", data)
        self.assertIn("reading_id", data)
        self.assertIn("criticality", data)
        self.assertIn("priority", data)
        self.assertIn("queue", data)
        self.assertIn("classification_time", data)
        self.assertIn("timestamp", data)

    def test_classify_endpoint_rejects_invalid_request(self):
        # missing device_code and non-numeric value
        payload = {
            "reading": {
                "device_code": "",
                "device_type": "cold_room",
                "sensor_name": "temperature",
                "value": "alto",
                "timestamp": "not-a-date",
            }
        }
        resp = self.client.post("/classification/classify", json=payload)
        # should be 400 or 422 depending on validation
        self.assertIn(resp.status_code, (400, 422))


if __name__ == "__main__":
    unittest.main()
