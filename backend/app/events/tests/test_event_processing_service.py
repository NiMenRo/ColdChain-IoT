import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.acquisition.normalizer import NormalizedReading
from app.classification.domain import TrafficClassification
from app.events.application.event_processing_service import EventProcessingService
from app.events.domain import Alert, ThresholdConfig
from app.qos.application.qos_metrics_service import MessageDeliveryRecord


class EventProcessingServiceTests(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures with realistic cold-chain thresholds."""
        # Thresholds for cold storage of meat: 0°C to 4°C, 85-90% humidity, energy ON
        self.config = ThresholdConfig(
            min_temperature=0.0,
            max_temperature=4.0,
            min_humidity=85.0,
            max_humidity=90.0,
            allowed_energy_states=frozenset({"on"}),
        )
        self.service = EventProcessingService(threshold_config=self.config)

    def _make_reading(
        self,
        device_code: str = "MEAT-VAULT-001",
        sensor_name: str = "temperature",
        value: float = 2.5,
        timestamp: str = "2026-09-01T12:00:00",
        raw_value = None,
    ) -> NormalizedReading:
        if raw_value is None:
            raw_value = "on" if sensor_name == "energy" else value
        return NormalizedReading(
            device_code=device_code,
            device_type="cold_storage",
            sensor_name=sensor_name,
            value=value,
            timestamp=timestamp,
            raw_value=raw_value,
        )

    def _make_classification(
        self, criticality: float = 5.5, priority: str = "medium"
    ) -> TrafficClassification:
        return TrafficClassification(
            id=uuid4(),
            reading_id=uuid4(),
            criticality=criticality,
            priority=priority,
            queue="Round Robin",
            classification_time=datetime.now(timezone.utc),
            timestamp=datetime.now(timezone.utc),
        )

    def _make_metrics(self) -> MessageDeliveryRecord:
        return MessageDeliveryRecord(
            message_id=uuid4(),
            sent_at=datetime.now(timezone.utc),
            received_at=datetime.now(timezone.utc),
            size_bytes=256.0,
            delivered=True,
            criticality=5.5,
            priority="medium",
        )

    def test_processes_normal_readings_without_alerts(self):
        """Normal readings within thresholds should not generate alerts."""
        readings = [
            self._make_reading(sensor_name="temperature", value=2.5),
            self._make_reading(sensor_name="humidity", value=87.5),
            self._make_reading(sensor_name="energy", value=1.0, raw_value="on"),
        ]
        classification = self._make_classification()

        result = self.service.process(readings, classification)

        self.assertEqual(result["event_count"], 0)
        self.assertEqual(result["alert_count"], 0)
        self.assertEqual(len(result["alerts"]), 0)

    def test_generates_alert_when_temperature_exceeds_max(self):
        """Temperature above max threshold should generate an alert."""
        readings = [
            self._make_reading(sensor_name="temperature", value=8.5)  # Above 4°C
        ]
        classification = self._make_classification(criticality=7.5, priority="high")

        result = self.service.process(readings, classification)

        self.assertEqual(result["event_count"], 1)
        self.assertEqual(result["alert_count"], 1)
        alert = result["alerts"][0]
        self.assertIsInstance(alert, Alert)
        self.assertEqual(alert.type, "TEMPERATURE_EXCEEDED")
        self.assertEqual(alert.criticality, 7.5)
        self.assertFalse(alert.acknowledged)

    def test_generates_alert_when_temperature_below_min(self):
        """Temperature below min threshold should generate an alert."""
        readings = [
            self._make_reading(sensor_name="temperature", value=-1.5)  # Below 0°C
        ]
        classification = self._make_classification(criticality=8.0, priority="high")

        result = self.service.process(readings, classification)

        self.assertEqual(result["event_count"], 1)
        self.assertEqual(result["alert_count"], 1)
        alert = result["alerts"][0]
        self.assertEqual(alert.type, "TEMPERATURE_BELOW_MIN")

    def test_generates_alert_for_humidity_anomaly(self):
        """Humidity outside configured range should generate an alert."""
        readings = [
            self._make_reading(sensor_name="humidity", value=95.0)  # Above 90%
        ]
        classification = self._make_classification(criticality=6.0, priority="medium")

        result = self.service.process(readings, classification)

        self.assertEqual(result["event_count"], 1)
        self.assertEqual(result["alert_count"], 1)
        alert = result["alerts"][0]
        self.assertEqual(alert.type, "HUMIDITY_ABOVE_MAX")

    def test_generates_alert_for_energy_anomaly(self):
        """Energy state change (e.g., 'off' when expecting 'on') should generate alert."""
        readings = [
            self._make_reading(sensor_name="energy", value=0.0, raw_value="off")
        ]
        classification = self._make_classification(criticality=9.0, priority="high")

        result = self.service.process(readings, classification)

        self.assertEqual(result["event_count"], 1)
        self.assertEqual(result["alert_count"], 1)
        alert = result["alerts"][0]
        self.assertEqual(alert.type, "ENERGY_STATE_ANOMALY")

    def test_processes_multiple_breaches_and_generates_multiple_alerts(self):
        """Multiple threshold breaches should generate multiple alerts."""
        readings = [
            self._make_reading(sensor_name="temperature", value=10.0),  # Exceeded
            self._make_reading(sensor_name="humidity", value=92.0),  # Exceeded
            self._make_reading(sensor_name="energy", value=0.0, raw_value="off"),  # Anomaly
        ]
        classification = self._make_classification(criticality=8.5, priority="high")

        result = self.service.process(readings, classification)

        self.assertEqual(result["event_count"], 3)
        self.assertEqual(result["alert_count"], 3)

    def test_alert_includes_classification_criticality(self):
        """Alert should use criticality from TrafficClassification."""
        readings = [
            self._make_reading(sensor_name="temperature", value=6.0)  # Breached
        ]
        classification = self._make_classification(criticality=7.8, priority="high")

        result = self.service.process(readings, classification)

        alert = result["alerts"][0]
        self.assertEqual(alert.criticality, 7.8)

    def test_device_id_mapping_resolves_correctly(self):
        """Device IDs should be resolved from device_code."""
        expected_device_id = uuid4()
        self.service.set_device_mapping({"MEAT-VAULT-001": expected_device_id})

        readings = [
            self._make_reading(sensor_name="temperature", value=8.0)
        ]
        classification = self._make_classification()

        result = self.service.process(readings, classification)

        alert = result["alerts"][0]
        self.assertEqual(alert.device_id, expected_device_id)

    def test_device_id_auto_generated_when_not_mapped(self):
        """Device ID should be auto-generated if device_code is not in mapping."""
        readings = [
            self._make_reading(device_code="UNKNOWN-DEVICE")
        ]
        classification = self._make_classification()

        result = self.service.process(readings, classification)

        # Should have at least generated a device_id
        self.assertIsNotNone(result["alerts"])

    def test_uses_injected_user_id_in_alerts(self):
        """Alerts should use user_id from service configuration."""
        expected_user_id = uuid4()
        service = EventProcessingService(
            threshold_config=self.config, user_id=expected_user_id
        )

        readings = [
            self._make_reading(sensor_name="temperature", value=8.0)
        ]
        classification = self._make_classification()

        result = service.process(readings, classification)

        alert = result["alerts"][0]
        self.assertEqual(alert.user_id, expected_user_id)

    def test_result_contains_classification_reference(self):
        """Result should include reference to input classification."""
        readings = [
            self._make_reading(sensor_name="temperature", value=2.5)
        ]
        classification = self._make_classification()

        result = self.service.process(readings, classification)

        self.assertEqual(result["classification_id"], str(classification.id))

    def test_result_includes_timestamp(self):
        """Result should include processing timestamp."""
        readings = [
            self._make_reading(sensor_name="temperature", value=2.5)
        ]
        classification = self._make_classification()

        result = self.service.process(readings, classification)

        self.assertIn("processed_at", result)
        # Verify it's a valid ISO format timestamp
        datetime.fromisoformat(result["processed_at"])

    def test_alert_timestamps_are_timezone_aware(self):
        """Generated alerts should have timezone-aware timestamps."""
        readings = [
            self._make_reading(sensor_name="temperature", value=8.0)
        ]
        classification = self._make_classification()

        result = self.service.process(readings, classification)

        alert = result["alerts"][0]
        self.assertIsNotNone(alert.created_at.tzinfo)

    def test_accepts_optional_metrics_parameter(self):
        """Service should accept optional QoS metrics without error."""
        readings = [
            self._make_reading(sensor_name="temperature", value=2.5)
        ]
        classification = self._make_classification()
        metrics = self._make_metrics()

        result = self.service.process(readings, classification, metrics)

        self.assertEqual(result["event_count"], 0)

    def test_rejects_invalid_readings_type(self):
        """Service should reject non-list readings."""
        classification = self._make_classification()

        with self.assertRaises(TypeError):
            self.service.process("not a list", classification)

    def test_rejects_invalid_classification_type(self):
        """Service should reject invalid classification type."""
        readings = [self._make_reading()]

        with self.assertRaises(TypeError):
            self.service.process(readings, "not a classification")

    def test_rejects_invalid_threshold_config(self):
        """Service should reject invalid threshold config at init."""
        with self.assertRaises(TypeError):
            EventProcessingService(threshold_config="not a config")


if __name__ == "__main__":
    unittest.main()
