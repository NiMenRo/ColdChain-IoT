import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.acquisition.pipeline import _worker_loop


class FakeQueue:
    """Minimal stand-in for MessageQueue exposing pop()."""

    def __init__(self, messages):
        self._messages = list(messages)

    def pop(self):
        if self._messages:
            return self._messages.pop(0)
        return None


class PipelineRiskEvaluationIntegrationTests(unittest.TestCase):
    """Verifies the acquisition pipeline evaluates I/U/R from the risk matrix."""

    def _run_worker(self, messages):
        app_state = type("State", (), {"classifications": []})()
        queue = FakeQueue(messages)
        stop_event = threading.Event()
        thread = threading.Thread(
            target=_worker_loop, args=(queue, app_state, stop_event), daemon=True
        )
        thread.start()

        deadline = time.time() + 10.0
        while len(app_state.classifications) < len(messages) * 3 and time.time() < deadline:
            time.sleep(0.05)

        stop_event.set()
        thread.join(timeout=2.0)
        return app_state.classifications

    def _message(self, **sensor_values):
        payload = {
            "device_code": "VITRINA-001",
            "device_type": "display_case",
            "timestamp": "2026-08-16T10:00:00",
        }
        payload.update(sensor_values)
        return {
            "payload": payload,
            "device_origin": {
                "device_code": "VITRINA-001",
                "device_type": "display_case",
            },
            "topic": "coldchain/device/VITRINA-001/telemetry",
            "received_at": "2026-08-16T10:00:00",
        }

    def test_critical_readings_produce_high_priority_wfq(self):
        message = self._message(temperature=9.5, humidity=98.0, energy="off")
        entries = self._run_worker([message])

        self.assertEqual(len(entries), 3)
        for entry in entries:
            classification = entry["classification"]
            self.assertGreaterEqual(classification.criticality, 7)
            self.assertEqual(classification.priority, "high")
            self.assertEqual(classification.queue, "WFQ")

        by_sensor = {entry["reading"].sensor_name: entry for entry in entries}
        self.assertEqual(by_sensor["temperature"]["classification"].criticality, 9)
        self.assertEqual(by_sensor["humidity"]["classification"].criticality, 8)
        self.assertEqual(by_sensor["energy"]["classification"].criticality, 9)

    def test_normal_readings_produce_low_priority_fifo(self):
        message = self._message(temperature=3.0, humidity=87.0, energy="on")
        entries = self._run_worker([message])

        self.assertEqual(len(entries), 3)
        for entry in entries:
            classification = entry["classification"]
            self.assertEqual(classification.criticality, 3)
            self.assertEqual(classification.priority, "low")
            self.assertEqual(classification.queue, "FIFO")

    def test_mixed_conditions_keep_sensor_level_granularity(self):
        # temperature in a critical band but humidity and energy fine.
        message = self._message(temperature=9.5, humidity=87.0, energy="on")
        entries = self._run_worker([message])

        by_sensor = {entry["reading"].sensor_name: entry for entry in entries}
        self.assertEqual(by_sensor["temperature"]["classification"].criticality, 9)
        self.assertEqual(by_sensor["temperature"]["classification"].priority, "high")
        self.assertEqual(by_sensor["humidity"]["classification"].criticality, 3)
        self.assertEqual(by_sensor["humidity"]["classification"].priority, "low")
        self.assertEqual(by_sensor["energy"]["classification"].criticality, 3)
        self.assertEqual(by_sensor["energy"]["classification"].priority, "low")


if __name__ == "__main__":
    unittest.main()