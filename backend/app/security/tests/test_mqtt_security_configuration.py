"""TSK-059 checks for the MQTT security boundary.

These tests deliberately validate the deployable Mosquitto configuration and
the client configuration without requiring broker passwords or certificates in
the repository.  A live broker test belongs to the optional integration suite
documented in ``docs/TSK-059-VALIDATION.md``.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-with-32-plus-bytes!!")

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.config import BackendConfig
from app.acquisition.infrastructure.mqtt_client import MQTTClient as BackendMQTTClient
from simulator.mqtt.client import MQTTClient as SimulatorMQTTClient


MQTT_DIRECTORY = REPOSITORY_ROOT / "docker" / "mqtt"


class MQTTConfigurationSecurityTests(unittest.TestCase):
    def test_mosquitto_only_exposes_tls_listener_with_authentication(self):
        config = (MQTT_DIRECTORY / "mosquitto.conf").read_text(encoding="utf-8")

        self.assertIn("listener 8883", config)
        self.assertNotIn("listener 1883", config)
        self.assertIn("tls_version tlsv1.2", config)
        self.assertIn("certfile /mosquitto/certs/server.crt", config)
        self.assertIn("keyfile /mosquitto/certs/server.key", config)
        self.assertIn("allow_anonymous false", config)
        self.assertIn("password_file /mosquitto/passwd", config)
        self.assertIn("acl_file /mosquitto/acl", config)

    def test_acl_grants_only_required_telemetry_operations(self):
        acl = (MQTT_DIRECTORY / "acl").read_text(encoding="utf-8")

        self.assertIn("user simulator", acl)
        self.assertIn("topic write coldchain/device/+/telemetry", acl)
        self.assertIn("user backend", acl)
        self.assertIn("topic read coldchain/device/+/telemetry", acl)
        self.assertNotIn("topic readwrite", acl)
        self.assertNotIn("topic #", acl)

    def test_runtime_config_refuses_missing_mqtt_credentials_or_ca(self):
        with self.assertRaises(RuntimeError):
            BackendConfig(
                mqtt_username="",
                mqtt_password="",
                mqtt_ca_cert="ca.pem",
            ).mqtt_credentials()
        with self.assertRaises(RuntimeError):
            BackendConfig(
                mqtt_username="backend",
                mqtt_password="secret",
                mqtt_ca_cert="",
            ).mqtt_credentials()

    def test_runtime_config_returns_credentials_and_ca_for_tls(self):
        config = BackendConfig(
            mqtt_username="backend",
            mqtt_password="not-logged",
            mqtt_ca_cert="ca.pem",
        )
        self.assertEqual(config.mqtt_credentials(), ("backend", "not-logged", "ca.pem"))

    @patch("app.acquisition.infrastructure.mqtt_client.mqtt.Client")
    def test_backend_client_configures_tls_and_credentials(self, client_factory):
        client = MagicMock()
        client_factory.return_value = client

        BackendMQTTClient(
            "broker.example", 8883, username="backend", password="secret", tls_ca_cert="ca.pem"
        )

        client.username_pw_set.assert_called_once_with("backend", "secret")
        client.tls_set.assert_called_once_with(ca_certs="ca.pem")

    @patch("simulator.mqtt.client.mqtt.Client")
    def test_simulator_client_configures_tls_and_credentials(self, client_factory):
        client = MagicMock()
        client_factory.return_value = client

        SimulatorMQTTClient(
            "broker.example", 8883, username="simulator", password="secret", tls_ca_cert="ca.pem"
        )

        client.username_pw_set.assert_called_once_with("simulator", "secret")
        client.tls_set.assert_called_once_with(ca_certs="ca.pem")


if __name__ == "__main__":
    unittest.main()
