from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.events.domain import RuleEvaluation


class TestRuleEvaluation(unittest.TestCase):
    def _make_valid(self, **overrides) -> RuleEvaluation:
        kwargs = dict(
            rule_id="temperature_threshold",
            device_code="dev-1",
            variable="temperature",
            observed_value=9.0,
            threshold=(2.0, 8.0),
            breached=True,
            evaluated_at=datetime.now(timezone.utc),
        )
        kwargs.update(overrides)
        return RuleEvaluation(**kwargs)

    def test_creates_valid_evaluation(self) -> None:
        evaluation = self._make_valid()
        self.assertIsInstance(evaluation, RuleEvaluation)

    def test_rejects_empty_rule_id(self) -> None:
        for value in ("", "   "):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self._make_valid(rule_id=value)

    def test_rejects_empty_device_code(self) -> None:
        for value in ("", "   "):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self._make_valid(device_code=value)

    def test_rejects_invalid_variable(self) -> None:
        with self.assertRaises(ValueError):
            self._make_valid(variable="pressure")

    def test_rejects_non_numeric_observed_temperature(self) -> None:
        for value in ("9", True, None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    self._make_valid(observed_value=value)

    def test_rejects_non_str_observed_energy(self) -> None:
        with self.assertRaises(TypeError):
            self._make_valid(
                variable="energy",
                observed_value=1.0,
                threshold=frozenset({"on"}),
            )

    def test_rejects_empty_observed_energy(self) -> None:
        with self.assertRaises(ValueError):
            self._make_valid(
                variable="energy",
                observed_value="   ",
                threshold=frozenset({"on"}),
            )

    def test_rejects_bad_threshold_type_for_temperature(self) -> None:
        with self.assertRaises(TypeError):
            self._make_valid(threshold=frozenset({"on"}))

    def test_rejects_ragged_threshold_tuple(self) -> None:
        with self.assertRaises(TypeError):
            self._make_valid(threshold=(2.0, 8.0, 1.0))

    def test_rejects_bad_threshold_type_for_energy(self) -> None:
        with self.assertRaises(TypeError):
            self._make_valid(
                variable="energy",
                observed_value="off",
                threshold=(2.0, 8.0),
            )

    def test_rejects_non_bool_breached(self) -> None:
        for value in ("yes", 1, 0, None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    self._make_valid(breached=value)

    def test_rejects_naive_evaluated_at(self) -> None:
        with self.assertRaises(TypeError):
            self._make_valid(evaluated_at=datetime.now())

    def test_rejects_non_datetime_evaluated_at(self) -> None:
        with self.assertRaises(TypeError):
            self._make_valid(evaluated_at="2024-01-01T00:00:00")


if __name__ == "__main__":
    unittest.main()
