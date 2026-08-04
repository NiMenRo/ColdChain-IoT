import logging

from sensors.energy_status_sensor import EnergyStatusSensor
from sensors.humidity_sensor import HumiditySensor
from sensors.temperature_sensor import TemperatureSensor

from .client import MQTTClient

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

    def publish_telemetry(self, device) -> bool:
        topic = f"{self._topic_prefix}/{device.code}/telemetry"
        payload = self._build_payload(device)
        logger.debug("Publicando telemetría de %s en %s", device.code, topic)
        return self._mqtt_client.publish(topic, payload, self._qos)

    def _build_payload(self, device) -> dict:
        readings = {}
        timestamp = None
        for sensor in device.get_sensors():
            key, measurement = self._read_sensor(sensor)
            if key is not None:
                readings[key] = measurement.value
                if timestamp is None:
                    timestamp = measurement.timestamp
        readings["device_code"] = device.code
        readings["device_type"] = device.device_type.value
        readings["timestamp"] = timestamp.isoformat(timespec="seconds") if timestamp else ""
        return readings

    def _read_sensor(self, sensor):
        for sensor_class, key in _SENSOR_MAP.items():
            if isinstance(sensor, sensor_class):
                return key, sensor.read()
        return None, None
