import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from app.acquisition.normalizer import TelemetryNormalizer
from app.classification.application.classification_service import ClassificationService
from app.classification.application.criticality_calculator import CriticalityCalculator
from app.classification.application.priority_assigner import PriorityAssigner
from app.classification.application.risk_matrix_evaluator import RiskMatrixEvaluator
from app.events.api import router as events_router
from app.events.application.event_processing_service import EventProcessingService
from app.events.domain import ThresholdConfig
from app.qos.application.traffic_planning_service import TrafficPlanningService
from simulator.devices import ColdRoom
from simulator.scenarios import CriticalScenario, CriticalScenarioManager
from simulator.sensors import (
    EnergyState,
    EnergyStatusSensor,
    HumiditySensor,
    TemperatureSensor,
)


class SimulatorEventIntegrationTests(unittest.TestCase):
    """Validate the full simulator -> classification -> QoS -> event flow."""

    def setUp(self):
        self.device = ColdRoom(
            id="DEV-SIM-001",
            code="CAVA-SIM-001",
            name="Cava de pruebas",
            location="Laboratorio",
        )
        self.temperature_sensor = TemperatureSensor(
            device=self.device,
            min_temperature=0.0,
            max_temperature=4.0,
        )
        self.humidity_sensor = HumiditySensor(device=self.device)
        self.energy_sensor = EnergyStatusSensor(device=self.device)
        self.device.add_sensor(self.temperature_sensor)
        self.device.add_sensor(self.humidity_sensor)
        self.device.add_sensor(self.energy_sensor)

        self.normalizer = TelemetryNormalizer()
        self.risk_evaluator = RiskMatrixEvaluator()
        self.classification_service = ClassificationService(
            calculator=CriticalityCalculator(),
            assigner=PriorityAssigner(),
        )
        self.qos_service = TrafficPlanningService()
        self.threshold_config = ThresholdConfig(
            min_temperature=0.0,
            max_temperature=4.0,
            min_humidity=85.0,
            max_humidity=90.0,
            allowed_energy_states=frozenset({"on"}),
        )
        self.event_service = EventProcessingService(threshold_config=self.threshold_config)

    def _build_simulator_message(self):
        temperature = self.temperature_sensor.read().value
        humidity = self.humidity_sensor.read().value
        energy = self.energy_sensor.read().value
        timestamp = datetime.now(timezone.utc).isoformat()

        return {
            "topic": f"devices/{self.device.code}/telemetry",
            "payload": {
                "temperature": temperature,
                "humidity": humidity,
                "energy": energy,
                "timestamp": timestamp,
            },
            "device_origin": {
                "device_code": self.device.code,
                "device_type": "cold_storage",
            },
            "received_at": timestamp,
        }

    def test_simulator_critical_scenario_generates_alerts_and_exposes_them_via_api(self):
        """The real simulator can drive the event pipeline and expose generated alerts."""
        scenario = CriticalScenario(
            id="SCN-SIM-001",
            name="Escenario crítico de prueba",
            devices=[self.device],
            temperature_range=(8.0, 12.0),
            humidity_range=(92.0, 100.0),
            energy_state=EnergyState.OFF,
            duration_seconds=0.2,
        )
        manager = CriticalScenarioManager()
        manager.activate(scenario)

        message = self._build_simulator_message()
        readings = self.normalizer.normalize(message)

        classifications = []
        for reading in readings:
            criteria = self.risk_evaluator.evaluate(reading)
            classification = self.classification_service.classify(
                reading=reading,
                impact=criteria.impact,
                urgency=criteria.urgency,
                risk=criteria.risk,
            )
            self.qos_service.plan(classification)
            classifications.append(classification)

        primary_classification = max(classifications, key=lambda item: item.criticality)
        result = self.event_service.process(readings, primary_classification)

        assert result["alert_count"] >= 1
        alert_types = {alert.type for alert in result["alerts"]}
        assert {"TEMPERATURE_EXCEEDED", "HUMIDITY_ABOVE_MAX", "ENERGY_STATE_ANOMALY"}.intersection(alert_types)

        app = FastAPI()
        app.state.events = result["events"]
        app.state.alerts = result["alerts"]
        app.state.enriched_events = []
        app.include_router(events_router)

        client = TestClient(app)

        alerts_response = client.get("/events/alerts")
        assert alerts_response.status_code == 200
        payload = alerts_response.json()
        assert payload["count"] == len(result["alerts"])

        events_response = client.get("/events/events")
        assert events_response.status_code == 200
        events_payload = events_response.json()
        assert events_payload["count"] == len(result["events"])

        summary_response = client.get("/events/summary")
        assert summary_response.status_code == 200
        summary_payload = summary_response.json()
        assert summary_payload["total_alerts"] >= 1
        assert summary_payload["total_events"] >= 1

        time.sleep(0.25)
        manager.update()
        assert manager.get_active_scenarios() == []

    def test_simulator_restores_normal_behavior_after_scenario_expires(self):
        """Scenario changes are temporary and are later restored automatically."""
        scenario = CriticalScenario(
            id="SCN-SIM-002",
            name="Escenario temporal",
            devices=[self.device],
            temperature_range=(8.0, 12.0),
            humidity_range=(92.0, 100.0),
            energy_state=EnergyState.OFF,
            duration_seconds=0.05,
        )
        manager = CriticalScenarioManager()
        manager.activate(scenario)
        self.temperature_sensor.read()
        self.humidity_sensor.read()
        self.energy_sensor.read()

        time.sleep(0.1)
        manager.update()

        assert manager.get_active_scenarios() == []
        assert self.temperature_sensor.min_temperature == 0.0
        assert self.temperature_sensor.max_temperature == 4.0
        assert self.humidity_sensor.min_humidity == 60.0
        assert self.humidity_sensor.max_humidity == 90.0
        assert self.energy_sensor.current_state == EnergyState.ON
