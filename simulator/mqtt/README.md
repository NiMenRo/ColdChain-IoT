# MQTT Module

MQTT client responsible for publishing simulated sensor readings to the broker. Encapsulates connection, topic management, and message serialization.

## Classes

- `MQTTClient`: handles broker connection, reconnection, and message publishing. Serializes payloads to JSON.
- `DevicePublisher`: builds aggregated telemetry payloads per device and publishes to `coldchain/device/{device_code}/telemetry`.

## Topic convention

```
coldchain/device/{device_code}/telemetry
```

## Payload

```json
{
  "device_code": "CAVA-001",
  "device_type": "cold_room",
  "temperature": 4.2,
  "humidity": 71.8,
  "energy": "on",
  "timestamp": "2026-07-20T21:30:15"
}
```

See `docs/mqtt-topics.md` for full specification.
