"""End-to-end integration test for the complete event processing pipeline."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.acquisition.normalizer import NormalizedReading, TelemetryNormalizer
from app.classification.application.classification_service import ClassificationService
from app.classification.application.criticality_calculator import CriticalityCalculator
from app.classification.application.priority_assigner import PriorityAssigner
from app.classification.application.risk_matrix_evaluator import RiskMatrixEvaluator
from app.events.application.event_processing_service import EventProcessingService
from app.events.domain import Alert, ThresholdConfig
from app.qos.application.traffic_planning_service import TrafficPlanningService


class EndToEndEventProcessingTests(unittest.TestCase):
    """Test the complete flow from MQTT message to alerts."""

    def setUp(self):
        """Set up the full pipeline."""
        # Initialize all services
        self.normalizer = TelemetryNormalizer()
        self.risk_evaluator = RiskMatrixEvaluator()
        self.calculator = CriticalityCalculator()
        self.assigner = PriorityAssigner()
        self.classification_service = ClassificationService(
            calculator=self.calculator, assigner=self.assigner
        )
        self.qos_service = TrafficPlanningService()
        
        # Cold-storage thresholds
        threshold_config = ThresholdConfig(
            min_temperature=0.0,
            max_temperature=4.0,
            min_humidity=85.0,
            max_humidity=90.0,
            allowed_energy_states=frozenset({"on"}),
        )
        self.event_service = EventProcessingService(threshold_config=threshold_config)

    def _simulate_mqtt_message(
        self,
        device_code: str = "MEAT-VAULT-001",
        temperature: float = 2.5,
        humidity: float = 87.5,
        energy: str = "on",
    ) -> dict:
        """Simulate an MQTT message payload."""
        return {
            "topic": f"devices/{device_code}/telemetry",
            "payload": {
                "temperature": temperature,
                "humidity": humidity,
                "energy": energy,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            "device_origin": {
                "device_code": device_code,
                "device_type": "cold_storage",
            },
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

    def test_normal_operation_produces_no_alerts(self):
        """Normal conditions should not produce alerts."""
        # Simulate MQTT message with normal conditions
        mqtt_message = self._simulate_mqtt_message(
            temperature=2.5, humidity=87.5, energy="on"
        )

        # Normalize
        readings = self.normalizer.normalize(mqtt_message)
        self.assertEqual(len(readings), 3)  # temperature, humidity, energy

        # Classify each reading
        all_classifications = []
        for reading in readings:
            criteria = self.risk_evaluator.evaluate(reading)
            classification = self.classification_service.classify(
                reading=reading,
                impact=criteria.impact,
                urgency=criteria.urgency,
                risk=criteria.risk,
            )
            all_classifications.append(classification)

        # Plan QoS for first classification
        self.qos_service.plan(all_classifications[0])

        # Process events with first classification
        result = self.event_service.process(readings, all_classifications[0])

        self.assertEqual(result["event_count"], 0)
        self.assertEqual(result["alert_count"], 0)

    def test_temperature_anomaly_triggers_alert(self):
        """Temperature exceeding max threshold should generate alert."""
        # Simulate MQTT message with high temperature
        mqtt_message = self._simulate_mqtt_message(
            temperature=8.5, humidity=87.5, energy="on"
        )

        # Normalize
        readings = self.normalizer.normalize(mqtt_message)

        # Classify (focus on temperature reading)
        temp_reading = next(r for r in readings if r.sensor_name == "temperature")
        criteria = self.risk_evaluator.evaluate(temp_reading)
        classification = self.classification_service.classify(
            reading=temp_reading,
            impact=criteria.impact,
            urgency=criteria.urgency,
            risk=criteria.risk,
        )

        # Plan QoS
        self.qos_service.plan(classification)

        # Process events
        result = self.event_service.process([temp_reading], classification)

        self.assertEqual(result["event_count"], 1)
        self.assertEqual(result["alert_count"], 1)
        alert = result["alerts"][0]
        self.assertIsInstance(alert, Alert)
        self.assertEqual(alert.type, "TEMPERATURE_EXCEEDED")
        self.assertGreaterEqual(alert.criticality, 5.0)

    def test_energy_loss_triggers_high_priority_alert(self):
        """Energy loss should trigger a high-criticality alert."""
        # Simulate MQTT message with energy OFF
        mqtt_message = self._simulate_mqtt_message(
            temperature=2.5, humidity=87.5, energy="off"
        )

        # Normalize
        readings = self.normalizer.normalize(mqtt_message)

        # Classify (focus on energy reading)
        energy_reading = next(r for r in readings if r.sensor_name == "energy")
        criteria = self.risk_evaluator.evaluate(energy_reading)
        classification = self.classification_service.classify(
            reading=energy_reading,
            impact=criteria.impact,
            urgency=criteria.urgency,
            risk=criteria.risk,
        )

        # Verify this is HIGH priority
        self.assertEqual(classification.priority, "high")

        # Plan QoS
        self.qos_service.plan(classification)

        # Process events
        result = self.event_service.process([energy_reading], classification)

        self.assertEqual(result["event_count"], 1)
        self.assertEqual(result["alert_count"], 1)
        alert = result["alerts"][0]
        self.assertEqual(alert.type, "ENERGY_STATE_ANOMALY")
        self.assertGreaterEqual(alert.criticality, 7.0)

    def test_multiple_anomalies_generate_multiple_alerts(self):
        """Multiple threshold breaches should generate multiple alerts."""
        # Simulate MQTT message with multiple anomalies
        mqtt_message = self._simulate_mqtt_message(
            temperature=10.0, humidity=92.0, energy="off"
        )

        # Normalize
        readings = self.normalizer.normalize(mqtt_message)
        self.assertEqual(len(readings), 3)

        # Process all readings with a single classification (using first reading's classification)
        first_reading = readings[0]
        criteria = self.risk_evaluator.evaluate(first_reading)
        classification = self.classification_service.classify(
            reading=first_reading,
            impact=criteria.impact,
            urgency=criteria.urgency,
            risk=criteria.risk,
        )

        # Process events with all readings
        result = self.event_service.process(readings, classification)

        # Should generate 3 alerts (one per anomaly)
        self.assertEqual(result["event_count"], 3)
        self.assertEqual(result["alert_count"], 3)

        # Verify we have different event types
        event_types = {event.event_type for event in result["events"]}
        self.assertIn("TEMPERATURE_EXCEEDED", event_types)
        self.assertIn("HUMIDITY_ABOVE_MAX", event_types)
        self.assertIn("ENERGY_STATE_ANOMALY", event_types)

    def test_qos_queuing_respects_priority(self):
        """QoS service should route alerts by priority."""
        # Create high-priority message (energy loss)
        mqtt_message = self._simulate_mqtt_message(energy="off")

        readings = self.normalizer.normalize(mqtt_message)
        energy_reading = next(r for r in readings if r.sensor_name == "energy")
        criteria = self.risk_evaluator.evaluate(energy_reading)
        high_classification = self.classification_service.classify(
            reading=energy_reading,
            impact=criteria.impact,
            urgency=criteria.urgency,
            risk=criteria.risk,
        )

        # Route through QoS
        self.qos_service.plan(high_classification)

        # Verify it went to HIGH priority queue
        self.assertEqual(high_classification.priority, "high")
        high_queue = self.qos_service.get_queue("high")
        self.assertIn(high_classification, high_queue)

    def test_full_pipeline_preserves_data_integrity(self):
        """Data should be preserved through the entire pipeline."""
        # Create realistic MQTT message
        device_code = "MEAT-VAULT-001"
        mqtt_message = self._simulate_mqtt_message(
            device_code=device_code, temperature=6.0
        )

        # Pass through pipeline
        readings = self.normalizer.normalize(mqtt_message)
        temp_reading = next(r for r in readings if r.sensor_name == "temperature")

        # Verify reading integrity
        self.assertEqual(temp_reading.device_code, device_code)
        self.assertEqual(temp_reading.sensor_name, "temperature")
        self.assertEqual(temp_reading.value, 6.0)

        # Classify
        criteria = self.risk_evaluator.evaluate(temp_reading)
        classification = self.classification_service.classify(
            reading=temp_reading,
            impact=criteria.impact,
            urgency=criteria.urgency,
            risk=criteria.risk,
        )

        # Verify classification integrity
        self.assertIsNotNone(classification.id)
        self.assertEqual(classification.priority, "medium")  # 6.0°C should be medium
        self.assertGreater(classification.criticality, 0)

        # Process through events
        result = self.event_service.process([temp_reading], classification)

        # Verify event integrity
        self.assertEqual(len(result["events"]), 1)
        event = result["events"][0]
        self.assertEqual(event.device_code, device_code)
        self.assertEqual(event.event_type, "TEMPERATURE_EXCEEDED")
        self.assertEqual(event.observed_value, 6.0)

        # Verify alert integrity
        alert = result["alerts"][0]
        self.assertEqual(alert.criticality, classification.criticality)
        self.assertEqual(alert.type, event.event_type)


if __name__ == "__main__":
    unittest.main()
