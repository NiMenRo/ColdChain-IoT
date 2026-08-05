import json
import sys
from time import sleep
from pathlib import Path

# Ensure repo root is on sys.path when running from backend/scripts
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import paho.mqtt.client as mqtt
except ImportError as exc:
    raise SystemExit("Falta paho-mqtt. Instálalo con: pip install paho-mqtt") from exc

HOST = "localhost"
PORT = 1883
TOPIC = "coldchain/device/CAVA-001/telemetry"
PAYLOAD = {
    "device_code": "CAVA-001",
    "device_type": "cold_room",
    "timestamp": "2026-08-04T10:00:00",
    "temperature": 4.5,
}

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="coldchain-test-publisher")
client.connect(HOST, PORT, 60)
client.loop_start()
client.publish(TOPIC, json.dumps(PAYLOAD), qos=0)
sleep(1)
client.loop_stop()
client.disconnect()
print(f"Mensaje publicado en {TOPIC}")
print(json.dumps(PAYLOAD, indent=2))
