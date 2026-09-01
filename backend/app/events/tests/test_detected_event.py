from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.events.domain import DetectedEvent


class TestDetectedEvent(unittest.TestCase):
    def _make_valid_kwargs(self, **overrides) -> dict:
        kwargs = {
            "id": uuid4(),
            "device_code": "REF-001",
            "variable": "temperature",
            "event_type": "TEMPERATURE_EXCEEDED",
            "message": "Temperatura observada (9.5°C) fuera del rango configurado (2.0-8.0°C)",
            "observed_value": 9.5,
            "threshold": (2.0, 8.0),
            "detected_at": datetime.now(timezone.utc),
        }
        kwargs.update(overrides)
        return kwargs

    def _make_valid_event(self, **overrides) -> DetectedEvent:
        return DetectedEvent(**self._make_valid_kwargs(**overrides))

    def test_creates_valid_event(self) -> None:
        event = self._make_valid_event()
        self.assertIsInstance(event, DetectedEvent)
        self.assertIsInstance(event.id, UUID)
        self.assertEqual(event.device_code, "REF-001")
        self.assertEqual(event.variable, "temperature")
        self.assertEqual(event.event_type, "TEMPERATURE_EXCEEDED")
        self.assertIsInstance(event.detected_at, datetime)

    def test_creates_energy_event(self) -> None:
        event = self._make_valid_event(
            variable="energy",
            event_type="ENERGY_STATE_ANOMALY",
            observed_value="off",
            threshold=frozenset({"on"}),
            message="Estado de energía observado ('off') fuera de los estados permitidos {'on'}",
        )
        self.assertEqual(event.variable, "energy")
        self.assertEqual(event.observed_value, "off")
        self.assertIsInstance(event.threshold, frozenset)

    def test_rejects_invalid_id(self) -> None:
        for value in ("not-a-uuid", None, 123):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    self._make_valid_event(id=value)

    def test_rejects_invalid_device_code(self) -> None:
        for value in (123, None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    self._make_valid_event(device_code=value)

    def test_rejects_empty_device_code(self) -> None:
        for value in ("", "   "):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self._make_valid_event(device_code=value)

    def test_rejects_invalid_variable(self) -> None:
        with self.assertRaises(ValueError):
            self._make_valid_event(variable="pressure")

    def test_rejects_empty_event_type(self) -> None:
        for value in ("", "   "):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self._make_valid_event(event_type=value)

    def test_rejects_non_str_event_type(self) -> None:
        for value in (123, None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    self._make_valid_event(event_type=value)

    def test_rejects_empty_message(self) -> None:
        for value in ("", "   "):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self._make_valid_event(message=value)

    def test_rejects_non_str_message(self) -> None:
        for value in (123, None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    self._make_valid_event(message=value)

    def test_rejects_non_numeric_observed_temperature(self) -> None:
        for value in ("9", True, None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    self._make_valid_event(observed_value=value)

    def test_rejects_non_str_observed_energy(self) -> None:
        with self.assertRaises(TypeError):
            self._make_valid_event(
                variable="energy",
                event_type="ENERGY_STATE_ANOMALY",
                observed_value=1.0,
                threshold=frozenset({"on"}),
                message="test",
            )

    def test_rejects_empty_observed_energy(self) -> None:
        with self.assertRaises(ValueError):
            self._make_valid_event(
                variable="energy",
                event_type="ENERGY_STATE_ANOMALY",
                observed_value="   ",
                threshold=frozenset({"on"}),
                message="test",
            )

    def test_rejects_bad_threshold_type_for_temperature(self) -> None:
        with self.assertRaises(TypeError):
            self._make_valid_event(threshold=frozenset({"on"}))

    def test_rejects_ragged_threshold_tuple(self) -> None:
        with self.assertRaises(TypeError):
            self._make_valid_event(threshold=(2.0, 8.0, 1.0))

    def test_rejects_bad_threshold_type_for_energy(self) -> None:
        with self.assertRaises(TypeError):
            self._make_valid_event(
                variable="energy",
                event_type="ENERGY_STATE_ANOMALY",
                observed_value="off",
                threshold=(2.0, 8.0),
                message="test",
            )

    def test_rejects_invalid_detected_at(self) -> None:
        for value in ("2024-01-01", None, 1700000000):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    self._make_valid_event(detected_at=value)

    def test_rejects_naive_detected_at(self) -> None:
        with self.assertRaises(TypeError):
            self._make_valid_event(detected_at=datetime.now())


if __name__ == "__main__":
    unittest.main()
