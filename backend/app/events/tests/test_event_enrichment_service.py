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


class EventEnrichmentServiceTests(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.service = EventEnrichmentService()
        self.device_id = uuid4()
        self.user_id = uuid4()
        self.alert_id = uuid4()
        self.classification_id = uuid4()
        self.reading_id = uuid4()

    def _make_alert(self) -> Alert:
        return Alert(
            id=self.alert_id,
            device_id=self.device_id,
            user_id=self.user_id,
            type="TEMPERATURE_EXCEEDED",
            message="Temperature exceeded configured maximum",
            criticality=7.5,
            acknowledged=False,
            created_at=datetime.now(timezone.utc),
        )

    def _make_device_info(self) -> DeviceInfo:
        return DeviceInfo(
            device_id=self.device_id,
            device_code="MEAT-VAULT-001",
            device_type="cold_storage",
            location="Warehouse Zone A",
        )

    def _make_classification(self) -> TrafficClassification:
        return TrafficClassification(
            id=self.classification_id,
            reading_id=self.reading_id,
            criticality=7.5,
            priority="high",
            queue="WFQ",
            classification_time=datetime.now(timezone.utc),
            timestamp=datetime.now(timezone.utc),
        )

    def _make_qos_context(self) -> QoSContext:
        return QoSContext(
            latency=0.45,
            jitter=0.02,
            throughput=2048.0,  # bytes/sec
            pdr=99.5,
            packet_loss=0.5,
        )

    def test_enriches_alert_correctly(self):
        """Enrichment should include all alert properties."""
        alert = self._make_alert()
        device_info = self._make_device_info()
        classification = self._make_classification()
        qos_context = self._make_qos_context()

        enriched = self.service.enrich(alert, device_info, classification, qos_context)

        self.assertIsInstance(enriched, EnrichedEvent)
        self.assertEqual(enriched.alert_id, alert.id)
        self.assertEqual(enriched.alert_type, alert.type)
        self.assertEqual(enriched.alert_message, alert.message)
        self.assertEqual(enriched.alert_criticality, alert.criticality)
        self.assertEqual(enriched.alert_acknowledged, alert.acknowledged)
        self.assertEqual(enriched.alert_created_at, alert.created_at)

    def test_enriches_device_info_correctly(self):
        """Enrichment should include all device context."""
        alert = self._make_alert()
        device_info = self._make_device_info()
        classification = self._make_classification()
        qos_context = self._make_qos_context()

        enriched = self.service.enrich(alert, device_info, classification, qos_context)

        self.assertEqual(enriched.device_id, device_info.device_id)
        self.assertEqual(enriched.device_code, device_info.device_code)
        self.assertEqual(enriched.device_type, device_info.device_type)
        self.assertEqual(enriched.device_location, device_info.location)

    def test_enriches_classification_correctly(self):
        """Enrichment should include all classification information."""
        alert = self._make_alert()
        device_info = self._make_device_info()
        classification = self._make_classification()
        qos_context = self._make_qos_context()

        enriched = self.service.enrich(alert, device_info, classification, qos_context)

        self.assertEqual(enriched.classification_id, classification.id)
        self.assertEqual(enriched.reading_id, classification.reading_id)
        self.assertEqual(enriched.traffic_priority, classification.priority)
        self.assertEqual(enriched.traffic_queue, classification.queue)
        self.assertEqual(enriched.classification_time, classification.classification_time)

    def test_enriches_qos_context_correctly(self):
        """Enrichment should include all QoS metrics."""
        alert = self._make_alert()
        device_info = self._make_device_info()
        classification = self._make_classification()
        qos_context = self._make_qos_context()

        enriched = self.service.enrich(alert, device_info, classification, qos_context)

        self.assertEqual(enriched.qos_latency, qos_context.latency)
        self.assertEqual(enriched.qos_jitter, qos_context.jitter)
        self.assertEqual(enriched.qos_throughput, qos_context.throughput)
        self.assertEqual(enriched.qos_pdr, qos_context.pdr)
        self.assertEqual(enriched.qos_packet_loss, qos_context.packet_loss)

    def test_preserves_timestamps_timezone_aware(self):
        """Enriched event should have timezone-aware timestamps."""
        alert = self._make_alert()
        device_info = self._make_device_info()
        classification = self._make_classification()
        qos_context = self._make_qos_context()

        enriched = self.service.enrich(alert, device_info, classification, qos_context)

        self.assertIsNotNone(enriched.alert_created_at.tzinfo)
        self.assertIsNotNone(enriched.classification_time.tzinfo)
        self.assertIsNotNone(enriched.sensor_timestamp.tzinfo)
        self.assertIsNotNone(enriched.enrichment_timestamp.tzinfo)

    def test_preserves_user_context(self):
        """Enriched event should preserve user_id from alert."""
        alert = self._make_alert()
        device_info = self._make_device_info()
        classification = self._make_classification()
        qos_context = self._make_qos_context()

        enriched = self.service.enrich(alert, device_info, classification, qos_context)

        self.assertEqual(enriched.user_id, alert.user_id)

    def test_rejects_invalid_alert_type(self):
        """Service should reject invalid alert type."""
        device_info = self._make_device_info()
        classification = self._make_classification()
        qos_context = self._make_qos_context()

        with self.assertRaises(TypeError):
            self.service.enrich("not an alert", device_info, classification, qos_context)

    def test_rejects_invalid_device_info_type(self):
        """Service should reject invalid device_info type."""
        alert = self._make_alert()
        classification = self._make_classification()
        qos_context = self._make_qos_context()

        with self.assertRaises(TypeError):
            self.service.enrich(alert, "not device info", classification, qos_context)

    def test_rejects_invalid_classification_type(self):
        """Service should reject invalid classification type."""
        alert = self._make_alert()
        device_info = self._make_device_info()
        qos_context = self._make_qos_context()

        with self.assertRaises(TypeError):
            self.service.enrich(alert, device_info, "not a classification", qos_context)

    def test_rejects_invalid_qos_context_type(self):
        """Service should reject invalid qos_context type."""
        alert = self._make_alert()
        device_info = self._make_device_info()
        classification = self._make_classification()

        with self.assertRaises(TypeError):
            self.service.enrich(alert, device_info, classification, "not qos")

    def test_validates_device_id_consistency(self):
        """Service should validate that device IDs match."""
        alert = self._make_alert()
        # Create device_info with different device_id
        different_device_info = DeviceInfo(
            device_id=uuid4(),  # Different!
            device_code="DIFFERENT-001",
            device_type="cold_storage",
        )
        classification = self._make_classification()
        qos_context = self._make_qos_context()

        with self.assertRaises(ValueError):
            self.service.enrich(alert, different_device_info, classification, qos_context)

    def test_enrich_from_delivery_record(self):
        """Service should enrich using MessageDeliveryRecord."""
        alert = self._make_alert()
        device_info = self._make_device_info()
        classification = self._make_classification()
        delivery_record = MessageDeliveryRecord(
            message_id="msg-001",
            sent_at=datetime.now(timezone.utc),
            received_at=datetime.now(timezone.utc),
            size_bytes=256.0,
            delivered=True,
            criticality=7.5,
            priority="high",
        )

        enriched = self.service.enrich_from_delivery_record(
            alert, device_info, classification, delivery_record
        )

        self.assertIsInstance(enriched, EnrichedEvent)
        self.assertEqual(enriched.alert_id, alert.id)
        self.assertEqual(enriched.device_id, device_info.device_id)
        self.assertEqual(enriched.classification_id, classification.id)

    def test_enriched_event_is_immutable(self):
        """EnrichedEvent should be immutable (frozen dataclass)."""
        alert = self._make_alert()
        device_info = self._make_device_info()
        classification = self._make_classification()
        qos_context = self._make_qos_context()

        enriched = self.service.enrich(alert, device_info, classification, qos_context)

        # Attempt to modify should raise
        with self.assertRaises(AttributeError):
            enriched.alert_type = "DIFFERENT_TYPE"

    def test_device_info_is_immutable(self):
        """DeviceInfo should be immutable (frozen dataclass)."""
        device_info = self._make_device_info()

        with self.assertRaises(AttributeError):
            device_info.device_code = "DIFFERENT-CODE"

    def test_device_info_with_optional_location(self):
        """DeviceInfo should support optional location."""
        device_info_without_location = DeviceInfo(
            device_id=uuid4(),
            device_code="DEVICE-001",
            device_type="cold_storage",
            location=None,
        )

        self.assertIsNone(device_info_without_location.location)

    def test_full_traceability_chain(self):
        """Enriched event should maintain full traceability chain."""
        alert = self._make_alert()
        device_info = self._make_device_info()
        classification = self._make_classification()
        qos_context = self._make_qos_context()

        enriched = self.service.enrich(alert, device_info, classification, qos_context)

        # Should be able to trace back to all original IDs
        self.assertEqual(enriched.alert_id, alert.id)
        self.assertEqual(enriched.device_id, device_info.device_id)
        self.assertEqual(enriched.classification_id, classification.id)
        self.assertEqual(enriched.reading_id, classification.reading_id)
        self.assertEqual(enriched.user_id, alert.user_id)

    def test_qos_context_immutable(self):
        """QoSContext should be immutable (frozen dataclass)."""
        qos_context = self._make_qos_context()

        with self.assertRaises(AttributeError):
            qos_context.pdr = 95.0


if __name__ == "__main__":
    unittest.main()
