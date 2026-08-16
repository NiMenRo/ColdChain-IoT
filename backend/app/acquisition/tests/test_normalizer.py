import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.acquisition.normalizer import TelemetryNormalizer


class TelemetryNormalizerTests(unittest.TestCase):
    def test_normalizes_multiple_sensor_readings_into_uniform_structure(self):
        normalizer = TelemetryNormalizer()
        message = {
            "payload": {
                "device_code": "CAVA-001",
                "device_type": "cold_room",
                "timestamp": "2026-08-04T10:00:00",
                "temperature": 4.5,
                "humidity": 67.2,
            },
            "device_origin": {
                "device_code": "CAVA-001",
                "device_type": "cold_room",
            },
        }

        normalized = normalizer.normalize(message)

        self.assertEqual(len(normalized), 2)
        self.assertEqual(normalized[0].device_code, "CAVA-001")
        self.assertEqual(normalized[0].sensor_name, "temperature")
        self.assertEqual(normalized[0].raw_value, 4.5)
        self.assertEqual(normalized[0].timestamp, "2026-08-04T10:00:00")
        self.assertEqual(normalized[1].sensor_name, "humidity")

    def test_normalizes_energy_state_strings_to_numeric_values(self):
        normalizer = TelemetryNormalizer()
        message = {
            "payload": {
                "device_code": "CAVA-001",
                "device_type": "cold_room",
                "timestamp": "2026-08-04T10:00:00",
                "energy": "off",
            },
            "device_origin": {
                "device_code": "CAVA-001",
                "device_type": "cold_room",
            },
        }

        normalized = normalizer.normalize(message)

        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0].sensor_name, "energy")
        self.assertEqual(normalized[0].value, 0.0)
        self.assertEqual(normalized[0].raw_value, "off")

    def test_rejects_messages_without_readable_fields(self):
        normalizer = TelemetryNormalizer()
        message = {
            "payload": {
                "device_code": "CAVA-001",
                "device_type": "cold_room",
                "timestamp": "2026-08-04T10:00:00",
            },
            "device_origin": {
                "device_code": "CAVA-001",
                "device_type": "cold_room",
            },
        }

        with self.assertRaises(ValueError):
            normalizer.normalize(message)


if __name__ == "__main__":
    unittest.main()
