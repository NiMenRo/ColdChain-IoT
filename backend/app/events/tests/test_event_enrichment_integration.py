import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.classification.domain import TrafficClassification
from app.events.application.event_enrichment_service import (
    DeviceInfo,
    EnrichedEvent,
    EventEnrichmentService,
    QoSContext,
)
from app.events.domain import Alert
from app.qos.application.qos_metrics_service import MessageDeliveryRecord


class EventEnrichmentIntegrationTests(unittest.TestCase):
    """Integration tests validating event enrichment in realistic scenarios."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = EventEnrichmentService()
        self.device_id = uuid4()
        self.user_id = uuid4()

    def _make_qos_context(
        self,
        latency: float = 0.1,
        jitter: float = 0.01,
        throughput: float = 1024.0,
        pdr: float = 99.5,
        packet_loss: float = 0.5,
    ) -> QoSContext:
        """Helper to create QoS context for testing."""
        return QoSContext(
            latency=latency,
            jitter=jitter,
            throughput=throughput,
            pdr=pdr,
            packet_loss=packet_loss,
        )

    def test_enrichment_preserves_full_traceability(self):
        """Enriched event should preserve complete trace from sensor to alert."""
        reading_id = uuid4()
        alert_id = uuid4()
        device_id = uuid4()
        user_id = uuid4()
        classification_id = uuid4()

        # Create alert that was triggered by a classification
        alert = Alert(
            id=alert_id,
            device_id=device_id,
            user_id=user_id,
            type="ENERGY_LOSS",
            message="Power loss detected on cold storage device",
            criticality=9.0,  # Maximum criticality
            acknowledged=False,
            created_at=datetime.now(timezone.utc),
        )

        # Device information
        device_info = DeviceInfo(
            device_id=device_id,
            device_code="MEAT-VAULT-001",
            device_type="cold_storage",
            location="Warehouse Zone A",
        )

        # Classification from earlier in pipeline
        classification = TrafficClassification(
            id=classification_id,
            reading_id=reading_id,
            criticality=9.0,
            priority="high",
            queue="WFQ",
            classification_time=datetime.now(timezone.utc),
            timestamp=datetime.now(timezone.utc),
        )

        # QoS metrics for this message
        qos_context = self._make_qos_context(
            latency=0.05,
            jitter=0.01,
            throughput=2048.0,
            pdr=99.8,
            packet_loss=0.2,
        )

        # Enrich the alert
        enriched = self.service.enrich(alert, device_info, classification, qos_context)

        # Verify traceability chain
        self.assertEqual(enriched.alert_id, alert_id, "Alert ID lost")
        self.assertEqual(enriched.device_id, device_id, "Device ID lost")
        self.assertEqual(enriched.user_id, user_id, "User ID lost")
        self.assertEqual(enriched.reading_id, reading_id, "Reading ID lost")
        self.assertEqual(enriched.classification_id, classification_id, "Classification ID lost")

    def test_enrichment_with_multiple_alerts_same_device(self):
        """Multiple alerts from same device should maintain independence."""
        device_id = uuid4()
        device_info = DeviceInfo(
            device_id=device_id,
            device_code="DEVICE-001",
            device_type="cold_storage",
        )

        # Create two independent alerts
        alerts = []
        enriched_events = []

        for i in range(2):
            alert = Alert(
                id=uuid4(),
                device_id=device_id,
                user_id=uuid4(),
                type="TEMPERATURE_EXCEEDED" if i == 0 else "HUMIDITY_ANOMALY",
                message=f"Alert {i}",
                criticality=5.0 + i,
                acknowledged=False,
                created_at=datetime.now(timezone.utc),
            )
            alerts.append(alert)

            classification = TrafficClassification(
                id=uuid4(),
                reading_id=uuid4(),
                criticality=5.0 + i,
                priority="medium" if i == 0 else "high",
                queue="RR" if i == 0 else "WFQ",
                classification_time=datetime.now(timezone.utc),
                timestamp=datetime.now(timezone.utc),
            )

            qos_context = self._make_qos_context(
                latency=0.1 * (i + 1),
                throughput=1024.0 * (i + 1),
                pdr=99.5 - (i * 0.5),
            )

            enriched = self.service.enrich(alert, device_info, classification, qos_context)
            enriched_events.append(enriched)

        # Verify each enriched event is independent
        self.assertNotEqual(
            enriched_events[0].alert_id,
            enriched_events[1].alert_id,
            "Alert IDs should be unique",
        )
        self.assertNotEqual(
            enriched_events[0].alert_type,
            enriched_events[1].alert_type,
            "Alert types should differ",
        )
        self.assertNotEqual(
            enriched_events[0].classification_id,
            enriched_events[1].classification_id,
            "Classification IDs should differ",
        )
        # But device should be the same
        self.assertEqual(
            enriched_events[0].device_id,
            enriched_events[1].device_id,
            "Device should be same",
        )

    def test_enrichment_maintains_criticality_throughout_flow(self):
        """Criticality should remain consistent across alert, classification, and enriched event."""
        criticality = 7.5

        alert = Alert(
            id=uuid4(),
            device_id=self.device_id,
            user_id=self.user_id,
            type="TEST",
            message="Test alert",
            criticality=criticality,
            acknowledged=False,
            created_at=datetime.now(timezone.utc),
        )

        device_info = DeviceInfo(
            device_id=self.device_id,
            device_code="TEST-001",
            device_type="test",
        )

        classification = TrafficClassification(
            id=uuid4(),
            reading_id=uuid4(),
            criticality=criticality,
            priority="high",
            queue="WFQ",
            classification_time=datetime.now(timezone.utc),
            timestamp=datetime.now(timezone.utc),
        )

        qos_context = self._make_qos_context()

        enriched = self.service.enrich(alert, device_info, classification, qos_context)

        self.assertEqual(
            enriched.alert_criticality,
            criticality,
            "Alert criticality lost in enrichment",
        )

    def test_enrichment_with_zero_qos_metrics(self):
        """Enrichment should handle edge case of zero QoS metrics."""
        alert = Alert(
            id=uuid4(),
            device_id=self.device_id,
            user_id=self.user_id,
            type="TEST",
            message="Test",
            criticality=5.0,
            acknowledged=False,
            created_at=datetime.now(timezone.utc),
        )

        device_info = DeviceInfo(
            device_id=self.device_id,
            device_code="TEST-001",
            device_type="test",
        )

        classification = TrafficClassification(
            id=uuid4(),
            reading_id=uuid4(),
            criticality=5.0,
            priority="medium",
            queue="RR",
            classification_time=datetime.now(timezone.utc),
            timestamp=datetime.now(timezone.utc),
        )

        # Create context with edge-case metrics
        qos_context = self._make_qos_context(
            latency=0.0,
            throughput=0.0,
            pdr=0.0,
            packet_loss=100.0,
        )

        enriched = self.service.enrich(alert, device_info, classification, qos_context)

        self.assertIsNotNone(enriched, "Enrichment failed on edge-case metrics")
        self.assertEqual(enriched.qos_throughput, 0.0, "Throughput should be 0")
        self.assertEqual(enriched.qos_pdr, 0.0, "PDR should be 0")

    def test_enrichment_timestamp_ordering(self):
        """Enrichment should preserve correct timestamp ordering."""
        alert_time = datetime.now(timezone.utc)
        classification_time = datetime.now(timezone.utc)
        sensor_time = datetime.now(timezone.utc)

        alert = Alert(
            id=uuid4(),
            device_id=self.device_id,
            user_id=self.user_id,
            type="TEST",
            message="Test",
            criticality=5.0,
            acknowledged=False,
            created_at=alert_time,
        )

        device_info = DeviceInfo(
            device_id=self.device_id,
            device_code="TEST-001",
            device_type="test",
        )

        classification = TrafficClassification(
            id=uuid4(),
            reading_id=uuid4(),
            criticality=5.0,
            priority="medium",
            queue="RR",
            classification_time=classification_time,
            timestamp=sensor_time,
        )

        qos_context = self._make_qos_context()

        enriched = self.service.enrich(alert, device_info, classification, qos_context)

        # Verify timestamps are preserved
        self.assertEqual(enriched.alert_created_at, alert_time)
        self.assertEqual(enriched.classification_time, classification_time)
        self.assertEqual(enriched.sensor_timestamp, sensor_time)

    def test_enriched_event_serializable_format(self):
        """Enriched event should contain only serializable fields."""
        alert = Alert(
            id=uuid4(),
            device_id=self.device_id,
            user_id=self.user_id,
            type="TEST",
            message="Test",
            criticality=5.0,
            acknowledged=False,
            created_at=datetime.now(timezone.utc),
        )

        device_info = DeviceInfo(
            device_id=self.device_id,
            device_code="TEST-001",
            device_type="test",
            location="Test Location",
        )

        classification = TrafficClassification(
            id=uuid4(),
            reading_id=uuid4(),
            criticality=5.0,
            priority="medium",
            queue="RR",
            classification_time=datetime.now(timezone.utc),
            timestamp=datetime.now(timezone.utc),
        )

        qos_context = self._make_qos_context()

        enriched = self.service.enrich(alert, device_info, classification, qos_context)

        # All fields should be basic Python types (for JSON serialization)
        self.assertIsInstance(enriched.alert_id, type(uuid4()))
        self.assertIsInstance(enriched.alert_type, str)
        self.assertIsInstance(enriched.alert_message, str)
        self.assertIsInstance(enriched.alert_criticality, (int, float))
        self.assertIsInstance(enriched.alert_acknowledged, bool)
        self.assertIsInstance(enriched.device_code, str)
        self.assertIsInstance(enriched.qos_latency, (int, float))


if __name__ == "__main__":
    unittest.main()
