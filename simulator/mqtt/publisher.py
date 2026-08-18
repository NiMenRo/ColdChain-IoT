import logging

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

    def publish_telemetry(self, device, measurements=None) -> bool:
        """Publica la telemetría de un dispositivo.

        Cuando se proporciona ``measurements`` (dict {sensor: measurement}), el
        payload se construye reutilizando esas mediciones ya capturadas, sin
        volver a llamar a ``sensor.read()``. Esto garantiza que la medición
        mostrada en consola y la publicada por MQTT sean exactamente la misma.
        """
        topic = f"{self._topic_prefix}/{device.code}/telemetry"
        payload = self._build_payload(device, measurements=measurements)
        logger.debug("Publicando telemetría de %s en %s", device.code, topic)
        return self._mqtt_client.publish(topic, payload, self._qos)

    def _build_payload(self, device, measurements=None) -> dict:
        readings = {}
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
                if timestamp is None:
                    timestamp = measurement.timestamp
        readings["device_code"] = device.code
        readings["device_type"] = device.device_type.value
        readings["timestamp"] = timestamp.isoformat(timespec="seconds") if timestamp else ""
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
