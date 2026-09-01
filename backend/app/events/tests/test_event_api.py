import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.classification.domain import TrafficClassification
from app.events.api import router
from app.events.application.event_enrichment_service import (
    DeviceInfo,
    EventEnrichmentService,
    QoSContext,
)
from app.events.domain import Alert, DetectedEvent


class EventProcessingAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.state.alerts = []
        self.app.state.events = []
        self.app.state.enriched_events = []
        self.app.include_router(router)
        self.client = TestClient(self.app)

        self.alert = Alert(
            id=uuid4(),
            device_id=uuid4(),
            user_id=uuid4(),
            type="TEMPERATURE_EXCEEDED",
            message="Temperature above limit",
            criticality=8.5,
            acknowledged=False,
            created_at=datetime.now(timezone.utc),
        )
        self.app.state.alerts.append(self.alert)

        self.detected = DetectedEvent(
            id=uuid4(),
            device_code="CAVA-001",
            variable="temperature",
            event_type="TEMPERATURE_EXCEEDED",
            message="Temperature above limit",
            observed_value=7.5,
            threshold=(0.0, 4.0),
            detected_at=datetime.now(timezone.utc),
        )
        self.app.state.events.append(self.detected)

        classification = TrafficClassification(
            id=uuid4(),
            reading_id=uuid4(),
            criticality=8.5,
            priority="high",
            queue="WFQ",
            classification_time=datetime.now(timezone.utc),
            timestamp=datetime.now(timezone.utc),
        )
        device_info = DeviceInfo(
            device_id=self.alert.device_id,
            device_code="CAVA-001",
            device_type="cold_storage",
            location="Warehouse A",
        )
        qos_context = QoSContext(
            latency=0.4,
            jitter=0.01,
            throughput=2200.0,
            pdr=99.2,
            packet_loss=0.8,
        )
        enriched = EventEnrichmentService().enrich(
            alert=self.alert,
            device_info=device_info,
            classification=classification,
            qos_context=qos_context,
        )
        self.app.state.enriched_events.append(enriched)

    def test_get_alerts_returns_list(self):
        response = self.client.get("/events/alerts")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["alerts"][0]["type"], "TEMPERATURE_EXCEEDED")

    def test_get_alert_by_id_returns_matching_alert(self):
        response = self.client.get(f"/events/alerts/{self.alert.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["alert"]["id"], str(self.alert.id))

    def test_get_events_returns_detected_events(self):
        response = self.client.get("/events/events")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["events"][0]["event_type"], "TEMPERATURE_EXCEEDED")

    def test_get_enriched_events_returns_context(self):
        response = self.client.get("/events/enriched")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["enriched_events"][0]["device_code"], "CAVA-001")
        self.assertEqual(data["enriched_events"][0]["traffic_queue"], "WFQ")

    def test_limit_zero_is_rejected(self):
        response = self.client.get("/events/alerts?limit=0")
        self.assertEqual(response.status_code, 400)
        self.assertIn("greater than zero", response.json()["detail"])

    def test_enriched_event_by_alert_id_returns_record(self):
        response = self.client.get(f"/events/enriched/{self.alert.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["enriched_event"]["alert_id"], str(self.alert.id))


if __name__ == "__main__":
    unittest.main()
