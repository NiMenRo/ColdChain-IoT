import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.acquisition.normalizer import NormalizedReading
from app.classification.application.risk_matrix_evaluator import (
    RiskCriteria,
    RiskMatrixEvaluator,
)


class RiskMatrixEvaluatorTests(unittest.TestCase):

    def setUp(self):
        self.evaluator = RiskMatrixEvaluator()

    def _make_reading(self, sensor_name, value, raw_value=None):
        return NormalizedReading(
            device_code="CAVA-001",
            device_type="cold_room",
            sensor_name=sensor_name,
            value=value,
            timestamp="2026-08-13T10:00:00",
            raw_value=value if raw_value is None else raw_value,
        )

    # -- temperature ----------------------------------------------------------

    def test_temperature_in_normal_range(self):
        criteria = self.evaluator.evaluate(self._make_reading("temperature", 2.0))
        self.assertEqual(criteria, RiskCriteria(impact=1, urgency=1, risk=1))

    def test_temperature_lower_boundary_zero(self):
        criteria = self.evaluator.evaluate_temperature(0.0)
        self.assertEqual(criteria, RiskCriteria(1, 1, 1))

    def test_temperature_upper_boundary_four(self):
        criteria = self.evaluator.evaluate_temperature(4.0)
        self.assertEqual(criteria, RiskCriteria(1, 1, 1))

    def test_temperature_just_above_four(self):
        criteria = self.evaluator.evaluate_temperature(4.1)
        self.assertEqual(criteria, RiskCriteria(2, 2, 2))

    def test_temperature_medium_range(self):
        criteria = self.evaluator.evaluate_temperature(6.0)
        self.assertEqual(criteria, RiskCriteria(2, 2, 2))

    def test_temperature_upper_boundary_eight(self):
        criteria = self.evaluator.evaluate_temperature(8.0)
        self.assertEqual(criteria, RiskCriteria(2, 2, 2))

    def test_temperature_above_eight(self):
        criteria = self.evaluator.evaluate_temperature(9.0)
        self.assertEqual(criteria, RiskCriteria(3, 3, 3))

    def test_temperature_below_five_boundary(self):
        criteria = self.evaluator.evaluate_temperature(-5.0)
        self.assertEqual(criteria, RiskCriteria(2, 2, 2))

    def test_temperature_below_five(self):
        criteria = self.evaluator.evaluate_temperature(-5.1)
        self.assertEqual(criteria, RiskCriteria(3, 3, 2))

    def test_temperature_below_zero(self):
        criteria = self.evaluator.evaluate_temperature(-2.0)
        self.assertEqual(criteria, RiskCriteria(2, 2, 2))

    # -- humidity -------------------------------------------------------------

    def test_humidity_in_optimal_band(self):
        criteria = self.evaluator.evaluate(self._make_reading("humidity", 87.0))
        self.assertEqual(criteria, RiskCriteria(impact=1, urgency=1, risk=1))

    def test_humidity_lower_optimal_boundary(self):
        criteria = self.evaluator.evaluate_humidity(85.0)
        self.assertEqual(criteria, RiskCriteria(1, 1, 1))

    def test_humidity_upper_optimal_boundary(self):
        criteria = self.evaluator.evaluate_humidity(90.0)
        self.assertEqual(criteria, RiskCriteria(1, 1, 1))

    def test_humidity_just_below_optimal(self):
        criteria = self.evaluator.evaluate_humidity(84.0)
        self.assertEqual(criteria, RiskCriteria(2, 2, 2))

    def test_humidity_just_below_optimal_boundary(self):
        criteria = self.evaluator.evaluate_humidity(80.0)
        self.assertEqual(criteria, RiskCriteria(2, 2, 2))

    def test_humidity_just_above_optimal(self):
        criteria = self.evaluator.evaluate_humidity(91.0)
        self.assertEqual(criteria, RiskCriteria(2, 2, 2))

    def test_humidity_above_optimal_boundary(self):
        criteria = self.evaluator.evaluate_humidity(95.0)
        self.assertEqual(criteria, RiskCriteria(2, 2, 2))

    def test_humidity_below_80(self):
        criteria = self.evaluator.evaluate_humidity(75.0)
        self.assertEqual(criteria, RiskCriteria(3, 3, 2))

    def test_humidity_above_95(self):
        criteria = self.evaluator.evaluate_humidity(98.0)
        self.assertEqual(criteria, RiskCriteria(3, 3, 2))

    # -- energy ---------------------------------------------------------------

    def test_energy_on(self):
        criteria = self.evaluator.evaluate(self._make_reading("energy", 1.0, raw_value="on"))
        self.assertEqual(criteria, RiskCriteria(impact=1, urgency=1, risk=1))

    def test_energy_off(self):
        criteria = self.evaluator.evaluate(self._make_reading("energy", 0.0, raw_value="off"))
        self.assertEqual(criteria, RiskCriteria(impact=3, urgency=3, risk=3))

    def test_energy_intermittent(self):
        criteria = self.evaluator.evaluate(self._make_reading("energy", 0.0, raw_value="intermittent"))
        self.assertEqual(criteria, RiskCriteria(impact=2, urgency=3, risk=2))

    def test_energy_case_insensitive(self):
        criteria = self.evaluator.evaluate_energy("OFF")
        self.assertEqual(criteria, RiskCriteria(3, 3, 3))

    def test_energy_unknown_state_raises(self):
        with self.assertRaises(ValueError):
            self.evaluator.evaluate_energy("standby")

    def test_energy_empty_state_raises(self):
        with self.assertRaises(ValueError):
            self.evaluator.evaluate(self._make_reading("energy", 0.0, raw_value="  "))

    # -- dispatch / validation ------------------------------------------------

    def test_unsupported_sensor_raises(self):
        reading = self._make_reading("voltage", 220.0)
        with self.assertRaises(ValueError):
            self.evaluator.evaluate(reading)

    def test_rejects_none_reading(self):
        with self.assertRaises(TypeError):
            self.evaluator.evaluate(None)

    def test_can_calculate_criticality_from_criteria(self):
        from app.classification.application.criticality_calculator import CriticalityCalculator

        criteria = self.evaluator.evaluate_temperature(9.0)
        criticality = CriticalityCalculator().calculate(
            criteria.impact, criteria.urgency, criteria.risk
        )
        self.assertEqual(criticality, 9)


if __name__ == "__main__":
    unittest.main()