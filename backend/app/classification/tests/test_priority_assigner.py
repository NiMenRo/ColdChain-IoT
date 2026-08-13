import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.classification.application.priority_assigner import PriorityAssigner, PriorityLevel


class PriorityAssignerTests(unittest.TestCase):

    def setUp(self):
        self.assigner = PriorityAssigner()

    # -- assign() tests: HIGH ------------------------------------------------

    def test_assign_high_max(self):
        self.assertEqual(self.assigner.assign(9), PriorityLevel.HIGH)

    def test_assign_high_boundary(self):
        self.assertEqual(self.assigner.assign(7), PriorityLevel.HIGH)

    def test_assign_high_representative(self):
        self.assertEqual(self.assigner.assign(8), PriorityLevel.HIGH)

    # -- assign() tests: MEDIUM ----------------------------------------------

    def test_assign_medium_upper(self):
        self.assertEqual(self.assigner.assign(6), PriorityLevel.MEDIUM)

    def test_assign_medium_boundary(self):
        self.assertEqual(self.assigner.assign(4), PriorityLevel.MEDIUM)

    def test_assign_medium_representative(self):
        self.assertEqual(self.assigner.assign(5), PriorityLevel.MEDIUM)

    # -- assign() tests: LOW -------------------------------------------------

    def test_assign_low_min(self):
        self.assertEqual(self.assigner.assign(3), PriorityLevel.LOW)

    def test_assign_low_representative(self):
        self.assertEqual(self.assigner.assign(3.5), PriorityLevel.LOW)

    # -- validation: type errors ---------------------------------------------

    def test_rejects_bool_true(self):
        with self.assertRaises(TypeError):
            self.assigner.assign(True)

    def test_rejects_bool_false(self):
        with self.assertRaises(TypeError):
            self.assigner.assign(False)

    def test_rejects_string(self):
        with self.assertRaises(TypeError):
            self.assigner.assign("7")

    def test_rejects_none(self):
        with self.assertRaises(TypeError):
            self.assigner.assign(None)

    # -- validation: range errors --------------------------------------------

    def test_rejects_below_min(self):
        with self.assertRaises(ValueError):
            self.assigner.assign(2)

    def test_rejects_above_max(self):
        with self.assertRaises(ValueError):
            self.assigner.assign(10)

    def test_rejects_zero(self):
        with self.assertRaises(ValueError):
            self.assigner.assign(0)

    def test_rejects_negative(self):
        with self.assertRaises(ValueError):
            self.assigner.assign(-1)


if __name__ == "__main__":
    unittest.main()
