from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.acquisition.normalizer import NormalizedReading
from app.events.application.rule_engine import RuleEngine
from app.events.domain import RuleEvaluation, ThresholdConfig


class TestRuleEngine(unittest.TestCase):
    def _make_config(self) -> ThresholdConfig:
        return ThresholdConfig(
            min_temperature=2.0,
            max_temperature=8.0,
            min_humidity=80.0,
            max_humidity=90.0,
            allowed_energy_states=frozenset({"on"}),
        )

    def _make_reading(self, sensor: str, value: float, raw_value=None) -> NormalizedReading:
        return NormalizedReading(
            device_code="dev-1",
            device_type="refrigerator",
            sensor_name=sensor,
            value=value,
            timestamp="2024-01-01T00:00:00",
            raw_value=raw_value if raw_value is not None else value,
        )

    def test_returns_one_evaluation_per_reading(self) -> None:
        readings = [
            self._make_reading("temperature", 5.0),
            self._make_reading("humidity", 85.0),
            self._make_reading("energy", 1.0, raw_value="on"),
        ]
        results = RuleEngine(self._make_config()).evaluate(readings)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(isinstance(r, RuleEvaluation) for r in results))

    def test_temperature_above_max_breached(self) -> None:
        result = RuleEngine(self._make_config()).evaluate(
            [self._make_reading("temperature", 9.0)]
        )[0]
        self.assertTrue(result.breached)

    def test_temperature_below_min_breached(self) -> None:
        result = RuleEngine(self._make_config()).evaluate(
            [self._make_reading("temperature", 1.0)]
        )[0]
        self.assertTrue(result.breached)

    def test_temperature_within_range_ok(self) -> None:
        result = RuleEngine(self._make_config()).evaluate(
            [self._make_reading("temperature", 5.0)]
        )[0]
        self.assertFalse(result.breached)

    def test_humidity_out_of_range_breached(self) -> None:
        result = RuleEngine(self._make_config()).evaluate(
            [self._make_reading("humidity", 75.0)]
        )[0]
        self.assertTrue(result.breached)

    def test_humidity_within_range_ok(self) -> None:
        result = RuleEngine(self._make_config()).evaluate(
            [self._make_reading("humidity", 88.0)]
        )[0]
        self.assertFalse(result.breached)

    def test_energy_off_breached(self) -> None:
        result = RuleEngine(self._make_config()).evaluate(
            [self._make_reading("energy", 0.0, raw_value="off")]
        )[0]
        self.assertTrue(result.breached)
        self.assertEqual(result.observed_value, "off")

    def test_energy_intermittent_breached(self) -> None:
        result = RuleEngine(self._make_config()).evaluate(
            [self._make_reading("energy", 0.0, raw_value="intermittent")]
        )[0]
        self.assertTrue(result.breached)

    def test_energy_on_ok(self) -> None:
        result = RuleEngine(self._make_config()).evaluate(
            [self._make_reading("energy", 1.0, raw_value="on")]
        )[0]
        self.assertFalse(result.breached)

    def test_energy_state_case_insensitive(self) -> None:
        result = RuleEngine(self._make_config()).evaluate(
            [self._make_reading("energy", 1.0, raw_value="ON")]
        )[0]
        self.assertFalse(result.breached)

    def test_evaluation_metadata(self) -> None:
        result = RuleEngine(self._make_config()).evaluate(
            [self._make_reading("temperature", 9.0)]
        )[0]
        self.assertEqual(result.rule_id, "temperature_threshold")
        self.assertEqual(result.device_code, "dev-1")
        self.assertEqual(result.variable, "temperature")
        self.assertEqual(result.threshold, (2.0, 8.0))
        self.assertIsInstance(result.evaluated_at, datetime)
        self.assertIsNotNone(result.evaluated_at.tzinfo)

    def test_unsupported_sensor_raises(self) -> None:
        with self.assertRaises(ValueError):
            RuleEngine(self._make_config()).evaluate(
                [self._make_reading("pressure", 1.0)]
            )

    def test_rejects_non_list_input(self) -> None:
        with self.assertRaises(TypeError):
            RuleEngine(self._make_config()).evaluate("not a list")

    def test_rejects_non_normalized_reading(self) -> None:
        with self.assertRaises(TypeError):
            RuleEngine(self._make_config()).evaluate([{"sensor_name": "temperature"}])

    def test_rejects_invalid_config(self) -> None:
        with self.assertRaises(TypeError):
            RuleEngine("not a config")


if __name__ == "__main__":
    unittest.main()
