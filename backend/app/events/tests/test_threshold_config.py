from __future__ import annotations

import unittest

from app.events.domain import ThresholdConfig


class TestThresholdConfig(unittest.TestCase):
    def _make_valid(self, **overrides) -> ThresholdConfig:
        kwargs = dict(
            min_temperature=2.0,
            max_temperature=8.0,
            min_humidity=80.0,
            max_humidity=90.0,
            allowed_energy_states=frozenset({"on"}),
        )
        kwargs.update(overrides)
        return ThresholdConfig(**kwargs)

    def test_creates_valid_config(self) -> None:
        config = self._make_valid()
        self.assertIsInstance(config, ThresholdConfig)

    def test_rejects_non_numeric_min_temperature(self) -> None:
        for value in ("2", True, None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    self._make_valid(min_temperature=value)

    def test_rejects_non_numeric_max_temperature(self) -> None:
        for value in ("8", True, None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    self._make_valid(max_temperature=value)

    def test_rejects_min_gt_max_temperature(self) -> None:
        with self.assertRaises(ValueError):
            self._make_valid(min_temperature=9.0, max_temperature=8.0)

    def test_rejects_non_numeric_min_humidity(self) -> None:
        for value in ("80", True, None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    self._make_valid(min_humidity=value)

    def test_rejects_non_numeric_max_humidity(self) -> None:
        for value in ("90", True, None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    self._make_valid(max_humidity=value)

    def test_rejects_min_gt_max_humidity(self) -> None:
        with self.assertRaises(ValueError):
            self._make_valid(min_humidity=95.0, max_humidity=90.0)

    def test_rejects_empty_energy_states(self) -> None:
        with self.assertRaises(ValueError):
            self._make_valid(allowed_energy_states=frozenset())

    def test_rejects_non_str_energy_state(self) -> None:
        with self.assertRaises(TypeError):
            self._make_valid(allowed_energy_states=frozenset({1, "on"}))

    def test_accepts_set_and_normalizes_to_frozenset(self) -> None:
        config = self._make_valid(allowed_energy_states={"on", "intermittent"})
        self.assertIsInstance(config.allowed_energy_states, frozenset)
        self.assertEqual(config.allowed_energy_states, frozenset({"on", "intermittent"}))


if __name__ == "__main__":
    unittest.main()
