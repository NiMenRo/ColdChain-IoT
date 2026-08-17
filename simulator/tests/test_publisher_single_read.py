import uuid
import unittest.mock as mock
from datetime import datetime

from simulator.devices import ColdRoom
from simulator.mqtt.publisher import DevicePublisher
from simulator.sensors import EnergyStatusSensor, HumiditySensor, TemperatureSensor

_SENSOR_KEYS = {
    TemperatureSensor: "temperature",
    HumiditySensor: "humidity",
    EnergyStatusSensor: "energy",
}


class FakeMQTTClient:
    """Replaces the real MQTT client to capture published payloads."""

    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0):
        self.published.append((topic, payload, qos))
        return True


def _make_device():
    code = f"DEV-{uuid.uuid4().hex[:6]}"
    device = ColdRoom(id=code, code=code, name="Cava Test", location="Lab")
    sensors = [
        TemperatureSensor(device=device, min_temperature=2.0, max_temperature=6.0),
        HumiditySensor(device=device, min_humidity=60.0, max_humidity=90.0),
        EnergyStatusSensor(device=device),
    ]
    for sensor in sensors:
        device.add_sensor(sensor)
    return device, sensors


def test_publish_uses_the_same_measurements_that_were_displayed():
    device, sensors = _make_device()

    # Capturamos exactamente una lectura por sensor: la que se muestra en consola.
    measurements = {}
    for sensor in sensors:
        measurements[sensor] = sensor.read()

    fake_client = FakeMQTTClient()
    publisher = DevicePublisher(fake_client, topic_prefix="coldchain/device", qos=0)

    # Si el publisher volviera a leer un sensor, el AssertionError rompe el test
    # (regresión de la doble lectura).
    patches = [
        mock.patch.object(sensor, "read", side_effect=AssertionError("publisher must not re-read sensors"))
        for sensor in sensors
    ]
    for patch in patches:
        patch.start()
    try:
        assert publisher.publish_telemetry(device, measurements) is True
    finally:
        for patch in patches:
            patch.stop()

    assert len(fake_client.published) == 1
    topic, payload, _qos = fake_client.published[0]

    assert topic == f"coldchain/device/{device.code}/telemetry"
    assert payload["device_code"] == device.code
    assert payload["device_type"] == device.device_type.value

    first_timestamp = measurements[sensors[0]].timestamp
    assert payload["timestamp"] == first_timestamp.isoformat(timespec="seconds")

    for sensor in sensors:
        key = _SENSOR_KEYS[type(sensor)]
        assert key in payload
        assert payload[key] == measurements[sensor].value


def test_publish_without_measurements_still_reads_sensors():
    device, sensors = _make_device()
    fake_client = FakeMQTTClient()
    publisher = DevicePublisher(fake_client, topic_prefix="coldchain/device", qos=0)

    assert publisher.publish_telemetry(device) is True

    assert len(fake_client.published) == 1
    _topic, payload, _qos = fake_client.published[0]
    for sensor in sensors:
        key = _SENSOR_KEYS[type(sensor)]
        assert key in payload
        assert isinstance(payload[key], (int, float, str))