"""MQTT resubscribe on reconnect (clean sessions forget subscriptions)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import paho.mqtt.client as mqtt

from app.acquisition.infrastructure.mqtt_client import MQTTClient


def _client():
    with patch.object(mqtt, "Client") as cls:
        inner = MagicMock()
        inner.subscribe.return_value = (mqtt.MQTT_ERR_SUCCESS, 1)
        cls.return_value = inner
        c = MQTTClient("localhost", 8883)
        return c, inner


def test_subscribe_registers_and_calls_broker():
    c, inner = _client()
    cb = MagicMock()
    c.subscribe("coldchain/device/+/telemetry", cb, qos=0)
    inner.subscribe.assert_called_once_with("coldchain/device/+/telemetry", qos=0)
    assert c._subscriptions == [("coldchain/device/+/telemetry", cb, 0)]


def test_reconnect_resubscribes_registered_topics():
    c, inner = _client()
    cb = MagicMock()
    c.subscribe("coldchain/device/+/telemetry", cb, qos=0)
    inner.reset_mock()
    # Simulate a broker reconnect: paho invokes on_connect again.
    c._on_connect(inner, None, {}, 0, None)
    inner.subscribe.assert_called_once_with("coldchain/device/+/telemetry", qos=0)


def test_failed_subscribe_is_reported(caplog):
    import logging

    c, inner = _client()
    inner.subscribe.return_value = (1, 0)
    with caplog.at_level(logging.ERROR, logger="app.acquisition.infrastructure.mqtt_client"):
        c.subscribe("coldchain/device/+/telemetry", MagicMock(), qos=0)
    assert any("falló" in r.message for r in caplog.records)
