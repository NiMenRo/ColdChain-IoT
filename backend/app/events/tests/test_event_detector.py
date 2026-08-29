from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import UUID

from app.events.application.event_detector import EventDetector
from app.events.domain import DetectedEvent, RuleEvaluation


class TestEventDetector(unittest.TestCase):
    def setUp(self) -> None:
        self.detector = EventDetector()

    def _make_evaluation(self, **overrides) -> RuleEvaluation:
        kwargs = dict(
            rule_id="temperature_threshold",
            device_code="REF-001",
            variable="temperature",
            observed_value=9.5,
            threshold=(2.0, 8.0),
            breached=True,
            evaluated_at=datetime.now(timezone.utc),
        )
        kwargs.update(overrides)
        return RuleEvaluation(**kwargs)

    def test_returns_empty_when_no_breaches(self) -> None:
        evaluations = [
            self._make_evaluation(breached=False),
        ]
        result = self.detector.detect(evaluations)
        self.assertEqual(result, [])

    def test_returns_empty_for_empty_list(self) -> None:
        result = self.detector.detect([])
        self.assertEqual(result, [])

    def test_detects_single_breach(self) -> None:
        evaluations = [self._make_evaluation(breached=True)]
        result = self.detector.detect(evaluations)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], DetectedEvent)

    def test_ignores_non_breached(self) -> None:
        evaluations = [
            self._make_evaluation(breached=False),
            self._make_evaluation(breached=True),
            self._make_evaluation(breached=False),
        ]
        result = self.detector.detect(evaluations)
        self.assertEqual(len(result), 1)

    def test_multiple_breaches_produce_multiple_events(self) -> None:
        evaluations = [
            self._make_evaluation(breached=True),
            self._make_evaluation(
                device_code="REF-002", variable="humidity",
                observed_value=75.0, threshold=(80.0, 90.0),
                breached=True,
            ),
            self._make_evaluation(
                variable="energy", observed_value="off",
                threshold=frozenset({"on"}), breached=True,
            ),
        ]
        result = self.detector.detect(evaluations)
        self.assertEqual(len(result), 3)

    def test_temperature_above_max_event_type(self) -> None:
        evaluation = self._make_evaluation(
            observed_value=9.5, threshold=(2.0, 8.0), breached=True,
        )
        result = self.detector.detect([evaluation])
        self.assertEqual(result[0].event_type, "TEMPERATURE_EXCEEDED")

    def test_temperature_below_min_event_type(self) -> None:
        evaluation = self._make_evaluation(
            observed_value=1.0, threshold=(2.0, 8.0), breached=True,
        )
        result = self.detector.detect([evaluation])
        self.assertEqual(result[0].event_type, "TEMPERATURE_BELOW_MIN")

    def test_humidity_above_max_event_type(self) -> None:
        evaluation = self._make_evaluation(
            variable="humidity", observed_value=95.0,
            threshold=(80.0, 90.0), breached=True,
        )
        result = self.detector.detect([evaluation])
        self.assertEqual(result[0].event_type, "HUMIDITY_ABOVE_MAX")

    def test_humidity_below_min_event_type(self) -> None:
        evaluation = self._make_evaluation(
            variable="humidity", observed_value=75.0,
            threshold=(80.0, 90.0), breached=True,
        )
        result = self.detector.detect([evaluation])
        self.assertEqual(result[0].event_type, "HUMIDITY_BELOW_MIN")

    def test_energy_anomaly_event_type(self) -> None:
        evaluation = self._make_evaluation(
            variable="energy", observed_value="off",
            threshold=frozenset({"on"}), breached=True,
        )
        result = self.detector.detect([evaluation])
        self.assertEqual(result[0].event_type, "ENERGY_STATE_ANOMALY")

    def test_message_contains_observed_and_threshold_temperature(self) -> None:
        evaluation = self._make_evaluation(
            observed_value=9.5, threshold=(2.0, 8.0), breached=True,
        )
        result = self.detector.detect([evaluation])
        msg = result[0].message
        self.assertIn("9.5°C", msg)
        self.assertIn("2.0°C-8.0°C", msg)

    def test_message_contains_observed_and_threshold_humidity(self) -> None:
        evaluation = self._make_evaluation(
            variable="humidity", observed_value=75.0,
            threshold=(80.0, 90.0), breached=True,
        )
        result = self.detector.detect([evaluation])
        msg = result[0].message
        self.assertIn("75.0%", msg)
        self.assertIn("80.0%-90.0%", msg)

    def test_message_contains_energy_state(self) -> None:
        evaluation = self._make_evaluation(
            variable="energy", observed_value="off",
            threshold=frozenset({"on"}), breached=True,
        )
        result = self.detector.detect([evaluation])
        msg = result[0].message
        self.assertIn("'off'", msg)
        self.assertIn("on", msg)

    def test_event_has_uuid(self) -> None:
        evaluation = self._make_evaluation(breached=True)
        result = self.detector.detect([evaluation])
        self.assertIsInstance(result[0].id, UUID)

    def test_event_has_detected_at(self) -> None:
        evaluation = self._make_evaluation(breached=True)
        result = self.detector.detect([evaluation])
        self.assertIsInstance(result[0].detected_at, datetime)
        self.assertIsNotNone(result[0].detected_at.tzinfo)

    def test_device_code_preserved(self) -> None:
        evaluation = self._make_evaluation(
            device_code="REF-003", breached=True,
        )
        result = self.detector.detect([evaluation])
        self.assertEqual(result[0].device_code, "REF-003")

    def test_variable_preserved(self) -> None:
        evaluation = self._make_evaluation(
            variable="humidity", observed_value=75.0,
            threshold=(80.0, 90.0), breached=True,
        )
        result = self.detector.detect([evaluation])
        self.assertEqual(result[0].variable, "humidity")

    def test_observed_value_preserved(self) -> None:
        evaluation = self._make_evaluation(
            observed_value=9.5, breached=True,
        )
        result = self.detector.detect([evaluation])
        self.assertEqual(result[0].observed_value, 9.5)

    def test_threshold_preserved(self) -> None:
        evaluation = self._make_evaluation(
            threshold=(2.0, 8.0), breached=True,
        )
        result = self.detector.detect([evaluation])
        self.assertEqual(result[0].threshold, (2.0, 8.0))

    def test_rejects_non_list_input(self) -> None:
        with self.assertRaises(TypeError):
            self.detector.detect("not a list")

    def test_rejects_non_rule_evaluation_items(self) -> None:
        with self.assertRaises(TypeError):
            self.detector.detect([{"breached": True}])

    def test_different_variables_independent(self) -> None:
        evaluations = [
            self._make_evaluation(
                variable="temperature", observed_value=9.5,
                threshold=(2.0, 8.0), breached=True,
            ),
            self._make_evaluation(
                variable="humidity", observed_value=75.0,
                threshold=(80.0, 90.0), breached=True,
            ),
        ]
        result = self.detector.detect(evaluations)
        variables = {e.variable for e in result}
        self.assertEqual(variables, {"temperature", "humidity"})


if __name__ == "__main__":
    unittest.main()
