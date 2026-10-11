"""TSK-059.3 — simulator publishes only DeviceSensor-enabled sensors."""

from simulator.devices import ColdRoom
from simulator.mqtt.publisher import DevicePublisher
from simulator.sensors import HumiditySensor, TemperatureSensor
from simulator.tests.test_publisher_single_read import FakeMQTTClient


def _make_partial_device():
    device = ColdRoom(id="DEV-PARTIAL", code="DEV-PARTIAL", name="Cava", location="Lab")
    device.add_sensor(TemperatureSensor(device=device, min_temperature=2.0, max_temperature=6.0))
    device.add_sensor(HumiditySensor(device=device, min_humidity=60.0, max_humidity=90.0))
    return device


def test_partial_device_publishes_only_enabled_sensors():
    device = _make_partial_device()
    measurements = {sensor: sensor.read() for sensor in device.get_sensors()}
    fake_client = FakeMQTTClient()
    publisher = DevicePublisher(fake_client, topic_prefix="coldchain/device", qos=0)
    assert publisher.publish_telemetry(device, measurements) is True
    assert len(fake_client.published) == 1
    _, payload, _ = fake_client.published[0]
    assert "temperature" in payload
    assert "humidity" in payload
    assert "energy" not in payload
    assert payload["device_code"] == device.code


def test_single_sensor_device_publishes_one_reading():
    device = ColdRoom(id="DEV-ONE", code="DEV-ONE", name="Cava", location="Lab")
    device.add_sensor(TemperatureSensor(device=device, min_temperature=2.0, max_temperature=6.0))
    measurements = {sensor: sensor.read() for sensor in device.get_sensors()}
    fake_client = FakeMQTTClient()
    publisher = DevicePublisher(fake_client, topic_prefix="coldchain/device", qos=0)
    assert publisher.publish_telemetry(device, measurements) is True
    _, payload, _ = fake_client.published[0]
    assert "temperature" in payload
    assert "humidity" not in payload
    assert "energy" not in payload
