import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.classification.application.criticality_calculator import (
    CriticalityCalculator,
    CriticalityLevel,
)


class CriticalityCalculatorTests(unittest.TestCase):

    def setUp(self):
        self.calc = CriticalityCalculator()

    # -- calculate() tests ---------------------------------------------------

    def test_calculate_all_high(self):
        self.assertEqual(self.calc.calculate(3, 3, 3), 9)

    def test_calculate_two_high_one_medium(self):
        self.assertEqual(self.calc.calculate(3, 3, 2), 8)

    def test_calculate_boundary_muy_critico(self):
        self.assertEqual(self.calc.calculate(2, 3, 2), 7)

    def test_calculate_all_medium(self):
        self.assertEqual(self.calc.calculate(2, 2, 2), 6)

    def test_calculate_boundary_medio(self):
        self.assertEqual(self.calc.calculate(1, 1, 2), 4)

    def test_calculate_all_low(self):
        self.assertEqual(self.calc.calculate(1, 1, 1), 3)

    # -- classify() tests ----------------------------------------------------

    def test_classify_high_upper(self):
        self.assertEqual(self.calc.classify(9), CriticalityLevel.HIGH)

    def test_classify_high_boundary(self):
        self.assertEqual(self.calc.classify(7), CriticalityLevel.HIGH)

    def test_classify_medium_upper(self):
        self.assertEqual(self.calc.classify(6), CriticalityLevel.MEDIUM)

    def test_classify_medium_boundary(self):
        self.assertEqual(self.calc.classify(4), CriticalityLevel.MEDIUM)

    def test_classify_low(self):
        self.assertEqual(self.calc.classify(3), CriticalityLevel.LOW)

    # -- validation: type errors ---------------------------------------------

    def test_rejects_zero(self):
        with self.assertRaises(ValueError):
            self.calc.calculate(0, 2, 2)

    def test_rejects_above_max(self):
        with self.assertRaises(ValueError):
            self.calc.calculate(4, 2, 2)

    def test_rejects_negative(self):
        with self.assertRaises(ValueError):
            self.calc.calculate(-1, 2, 2)

    def test_rejects_float(self):
        with self.assertRaises(TypeError):
            self.calc.calculate(1.5, 2, 2)

    def test_rejects_string(self):
        with self.assertRaises(TypeError):
            self.calc.calculate("3", 2, 2)

    def test_rejects_none(self):
        with self.assertRaises(TypeError):
            self.calc.calculate(None, 2, 2)

    def test_rejects_bool_true(self):
        with self.assertRaises(TypeError):
            self.calc.calculate(True, 2, 2)

    def test_rejects_bool_false(self):
        with self.assertRaises(TypeError):
            self.calc.calculate(False, 2, 2)

    def test_rejects_urgency_zero(self):
        with self.assertRaises(ValueError):
            self.calc.calculate(2, 0, 2)

    def test_rejects_risk_above_max(self):
        with self.assertRaises(ValueError):
            self.calc.calculate(2, 2, 4)


if __name__ == "__main__":
    unittest.main()
