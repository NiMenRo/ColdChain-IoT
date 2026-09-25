import json
import os
import sys
from time import sleep
from pathlib import Path

# Ensure repo root is on sys.path when running from backend/scripts
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import paho.mqtt.client as mqtt
except ImportError as exc:
    raise SystemExit("Falta paho-mqtt. Instálalo con: pip install paho-mqtt") from exc

# TSK-056: TLS + auth desde entorno (sin credenciales hardcodeadas).
# QoS 0 sin cambios.
HOST = os.getenv("MQTT_HOST", "localhost")
PORT = int(os.getenv("MQTT_PORT", "8883"))
USERNAME = os.getenv("MQTT_USERNAME", "")
PASSWORD = os.getenv("MQTT_PASSWORD", "")
CA_CERT = os.getenv("MQTT_CA_CERT", "")
TOPIC = "coldchain/device/CAVA-001/telemetry"
PAYLOAD = {
    "device_code": "CAVA-001",
    "device_type": "cold_room",
    "timestamp": "2026-08-04T10:00:00",
    "temperature": 4.5,
}

if not USERNAME or not PASSWORD:
    raise SystemExit("MQTT_USERNAME y MQTT_PASSWORD deben estar exportados (ver backend/.env.example).")
if not CA_CERT:
    raise SystemExit("MQTT_CA_CERT debe apuntar al CA local (ver backend/.env.example).")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="coldchain-test-publisher")
client.username_pw_set(USERNAME, PASSWORD)
client.tls_set(ca_certs=CA_CERT)
client.connect(HOST, PORT, 60)
client.loop_start()
client.publish(TOPIC, json.dumps(PAYLOAD), qos=0)
sleep(1)
client.loop_stop()
client.disconnect()
print(f"Mensaje publicado en {TOPIC}")
print(json.dumps(PAYLOAD, indent=2))
