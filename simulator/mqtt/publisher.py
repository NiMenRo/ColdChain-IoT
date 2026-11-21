import logging
import os
import threading
from collections import defaultdict
from datetime import timezone
from uuid import uuid4

from .client import MQTTClient

try:
    from sensors import EnergyStatusSensor, HumiditySensor, TemperatureSensor
except ModuleNotFoundError:  # pragma: no cover - fallback for package-style imports
    from simulator.sensors import EnergyStatusSensor, HumiditySensor, TemperatureSensor

logger = logging.getLogger(__name__)

_SENSOR_MAP = {
    TemperatureSensor:  "temperature",
    HumiditySensor:     "humidity",
    EnergyStatusSensor: "energy",
}


class DevicePublisher:

    def __init__(self, mqtt_client: MQTTClient, topic_prefix: str = "coldchain/device", qos: int = 0):
        self._mqtt_client = mqtt_client
        self._topic_prefix = topic_prefix
        self._qos = qos
        self._session_id = str(uuid4())
        self._sequences = defaultdict(int)
        self._sequence_lock = threading.Lock()

    def publish_telemetry(self, device, measurements=None) -> bool:
        """Publish telemetry for a device.

        When ``measurements`` (dict {sensor: measurement}) is provided, the
        payload is built by reusing those already captured measurements,
        without calling ``sensor.read()`` again. This ensures the
        measurement shown in the console and the one published via MQTT
        are exactly the same.
        """
        topic = f"{self._topic_prefix}/{device.code}/telemetry"
        payload = self._build_payload(device, measurements=measurements)
        with self._sequence_lock:
            sequence = self._sequences[device.code]
            self._sequences[device.code] += 1
        payload["trace"] = {
            "message_id": str(uuid4()),
            "producer_session_id": self._session_id,
            "sequence": sequence,
            "run_id": os.getenv("COLDCHAIN_RUN_ID") or None,
            "clock_domain": os.getenv("TELEMETRY_CLOCK_DOMAIN") or None,
        }
        logger.debug("Publishing telemetry for %s to %s", device.code, topic)
        return self._mqtt_client.publish(topic, payload, self._qos)

    def _build_payload(self, device, measurements=None) -> dict:
        readings = {}
        reading_timestamps = {}
        timestamp = None
        for sensor in device.get_sensors():
            if measurements is not None:
                if sensor not in measurements:
                    continue
                key = self._sensor_key(sensor)
                measurement = measurements[sensor]
            else:
                key, measurement = self._read_sensor(sensor)
            if key is not None and measurement is not None:
                readings[key] = measurement.value
                measured_at = measurement.timestamp
                if measured_at.tzinfo is None:
                    measured_at = measured_at.replace(tzinfo=timezone.utc)
                reading_timestamps[key] = measured_at.isoformat(timespec="microseconds")
                if timestamp is None:
                    timestamp = measurement.timestamp
        readings["device_code"] = device.code
        readings["device_type"] = device.device_type.value
        # TSK-059.7 — sensor timestamp as aware UTC with millisecond precision.
        # This is generation time, never a substitute for ingestion time.
        if timestamp is not None and timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        readings["timestamp"] = timestamp.isoformat(timespec="milliseconds") if timestamp else ""
        readings["reading_timestamps"] = reading_timestamps
        return readings

    def _sensor_key(self, sensor):
        for sensor_class, key in _SENSOR_MAP.items():
            if isinstance(sensor, sensor_class):
                return key
        return None

    def _read_sensor(self, sensor):
        key = self._sensor_key(sensor)
        if key is None:
            return None, None
        return key, sensor.read()
