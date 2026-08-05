import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.acquisition.normalizer import NormalizedReading
from app.classification.preparator import ClassificationPreparator


class ClassificationPreparatorTests(unittest.TestCase):
    def test_prepares_all_normalized_readings_for_classification(self):
        received = []

        def consumer(packet):
            received.append(packet)

        preparator = ClassificationPreparator(consumer=consumer)
        readings = [
            NormalizedReading(
                device_code="CAVA-001",
                device_type="cold_room",
                sensor_name="temperature",
                value=4.5,
                timestamp="2026-08-04T10:00:00",
                raw_value=4.5,
            ),
            NormalizedReading(
                device_code="CAVA-001",
                device_type="cold_room",
                sensor_name="humidity",
                value=67.2,
                timestamp="2026-08-04T10:00:00",
                raw_value=67.2,
            ),
        ]

        packets = preparator.prepare(readings)

        self.assertEqual(len(packets), 2)
        self.assertEqual(len(received), 2)
        self.assertEqual(packets[0].metadata["device_code"], "CAVA-001")
        self.assertEqual(packets[0].reading.sensor_name, "temperature")
        self.assertEqual(packets[0].metadata["timestamp"], "2026-08-04T10:00:00")


if __name__ == "__main__":
    unittest.main()
