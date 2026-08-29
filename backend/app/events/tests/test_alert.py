from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.events.domain import Alert


class TestAlert(unittest.TestCase):
    def _make_valid_kwargs(self) -> dict:
        return {
            "id": uuid4(),
            "device_id": uuid4(),
            "user_id": uuid4(),
            "type": "TEMPERATURE_EXCEEDED",
            "message": "Temperature above safe threshold",
            "criticality": 8.0,
            "acknowledged": False,
            "created_at": datetime.now(timezone.utc),
        }

    def _make_valid_alert(self) -> Alert:
        return Alert(**self._make_valid_kwargs())

    def test_creates_valid_alert(self) -> None:
        alert = self._make_valid_alert()
        self.assertIsInstance(alert, Alert)
        self.assertIsInstance(alert.id, UUID)
        self.assertIsInstance(alert.device_id, UUID)
        self.assertIsInstance(alert.user_id, UUID)
        self.assertIsInstance(alert.type, str)
        self.assertIsInstance(alert.message, str)
        self.assertIsInstance(alert.criticality, float)
        self.assertIsInstance(alert.acknowledged, bool)
        self.assertIsInstance(alert.created_at, datetime)

    def test_accepts_boundary_criticality_values(self) -> None:
        for value in (3, 3.0, 9, 9.0, 5.5):
            with self.subTest(value=value):
                kwargs = self._make_valid_kwargs()
                kwargs["criticality"] = value
                alert = Alert(**kwargs)
                self.assertEqual(alert.criticality, value)

    def test_rejects_invalid_id(self) -> None:
        for value in ("not-a-uuid", None, 123):
            with self.subTest(value=value):
                kwargs = self._make_valid_kwargs()
                kwargs["id"] = value
                with self.assertRaises(TypeError):
                    Alert(**kwargs)

    def test_rejects_invalid_device_id(self) -> None:
        for value in ("not-a-uuid", None, 123):
            with self.subTest(value=value):
                kwargs = self._make_valid_kwargs()
                kwargs["device_id"] = value
                with self.assertRaises(TypeError):
                    Alert(**kwargs)

    def test_rejects_invalid_user_id(self) -> None:
        for value in ("not-a-uuid", None, 123):
            with self.subTest(value=value):
                kwargs = self._make_valid_kwargs()
                kwargs["user_id"] = value
                with self.assertRaises(TypeError):
                    Alert(**kwargs)

    def test_rejects_invalid_type(self) -> None:
        for value in (123, None):
            with self.subTest(value=value):
                kwargs = self._make_valid_kwargs()
                kwargs["type"] = value
                with self.assertRaises(TypeError):
                    Alert(**kwargs)

    def test_rejects_empty_type(self) -> None:
        for value in ("", "   "):
            with self.subTest(value=value):
                kwargs = self._make_valid_kwargs()
                kwargs["type"] = value
                with self.assertRaises(ValueError):
                    Alert(**kwargs)

    def test_rejects_invalid_message(self) -> None:
        for value in (123, None):
            with self.subTest(value=value):
                kwargs = self._make_valid_kwargs()
                kwargs["message"] = value
                with self.assertRaises(TypeError):
                    Alert(**kwargs)

    def test_rejects_empty_message(self) -> None:
        for value in ("", "   "):
            with self.subTest(value=value):
                kwargs = self._make_valid_kwargs()
                kwargs["message"] = value
                with self.assertRaises(ValueError):
                    Alert(**kwargs)

    def test_rejects_non_numeric_criticality(self) -> None:
        for value in ("high", None, [8]):
            with self.subTest(value=value):
                kwargs = self._make_valid_kwargs()
                kwargs["criticality"] = value
                with self.assertRaises(TypeError):
                    Alert(**kwargs)

    def test_rejects_boolean_criticality(self) -> None:
        for value in (True, False):
            with self.subTest(value=value):
                kwargs = self._make_valid_kwargs()
                kwargs["criticality"] = value
                with self.assertRaises(TypeError):
                    Alert(**kwargs)

    def test_rejects_non_boolean_acknowledged(self) -> None:
        for value in ("yes", 1, 0, None):
            with self.subTest(value=value):
                kwargs = self._make_valid_kwargs()
                kwargs["acknowledged"] = value
                with self.assertRaises(TypeError):
                    Alert(**kwargs)

    def test_accepts_boolean_acknowledged(self) -> None:
        for value in (True, False):
            with self.subTest(value=value):
                kwargs = self._make_valid_kwargs()
                kwargs["acknowledged"] = value
                alert = Alert(**kwargs)
                self.assertEqual(alert.acknowledged, value)

    def test_rejects_invalid_created_at(self) -> None:
        for value in ("2024-01-01", None, 1700000000):
            with self.subTest(value=value):
                kwargs = self._make_valid_kwargs()
                kwargs["created_at"] = value
                with self.assertRaises(TypeError):
                    Alert(**kwargs)


if __name__ == "__main__":
    unittest.main()
