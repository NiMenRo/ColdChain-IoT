import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.acquisition.device_origin_identifier import DeviceOriginIdentifier
from app.acquisition.infrastructure.mqtt_subscriber import MQTTSubscriber
from app.acquisition.message_queue import MessageQueue


class DeviceOriginIdentifierTests(unittest.TestCase):
    def test_identifies_device_from_validated_payload(self):
        queue = MessageQueue()
        subscriber = MQTTSubscriber(queue)
        payload = {
            "device_code": "CAVA-001",
            "device_type": "cold_room",
            "timestamp": "2026-08-04T10:00:00",
            "temperature": 4.5,
        }
        msg = SimpleNamespace(
            payload=json.dumps(payload).encode("utf-8"),
            topic="coldchain/device/CAVA-001/telemetry",
        )

        subscriber.on_message(None, None, msg)

        self.assertEqual(len(queue.get_all()), 1)
        stored_message = queue.get_all()[0]
        self.assertEqual(stored_message["device_origin"]["device_code"], "CAVA-001")
        self.assertEqual(stored_message["device_origin"]["device_type"], "cold_room")

    def test_rejects_payload_without_device_identification(self):
        queue = MessageQueue()
        subscriber = MQTTSubscriber(queue)
        payload = {
            "device_code": "",
            "device_type": "cold_room",
            "timestamp": "2026-08-04T10:00:00",
            "temperature": 4.5,
        }
        msg = SimpleNamespace(
            payload=json.dumps(payload).encode("utf-8"),
            topic="coldchain/device/CAVA-001/telemetry",
        )

        subscriber.on_message(None, None, msg)

        self.assertEqual(queue.get_all(), [])
        self.assertEqual(len(subscriber.validator.get_invalid_messages()), 1)


if __name__ == "__main__":
    unittest.main()
