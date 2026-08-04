# Convención de tópicos MQTT

Este documento define la convención de tópicos y el esquema del payload JSON que
utilizarán el simulador (publicador) y el backend (suscriptor) en las tareas
TSK-008 y TSK-009.

## Tópicos

```
coldchain/device/{device_code}/telemetry
```

- `coldchain`: raíz del proyecto (espacio de nombres).
- `device`: categoría (dispositivos IoT).
- `{device_code}`: código del dispositivo, por ejemplo `CAVA-001`, `VITRINA-001`
  (campo `Device.code` del simulador).
- `telemetry`: tipo de mensaje, lectura agregada del ciclo de muestreo del
  dispositivo.

### Ejemplos

- `coldchain/device/CAVA-001/telemetry`
- `coldchain/device/VITRINA-001/telemetry`

### Suscripciones con comodines

- Todos los dispositivos (backend): `coldchain/device/+/telemetry`
- Filtro por prefijo de código: `coldchain/device/CAVA-+/telemetry`

### Tópicos reservados

`coldchain/device/{device_code}/status`: estado de conexión del dispositivo
(LWT). Reservado para una tarea futura, no se utiliza en TSK-007.

## Payload JSON

Ejemplo:

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

| Campo | Origen en el código del simulador | Notas |
|---|---|---|
| `device_code` | `Device.code` | Código del dispositivo emisor. |
| `device_type` | `Device.device_type.value` | `cold_room` o `refrigerated_showcase`. |
| `temperature` | `TemperatureSensor.read().value` | Grados Celsius, 1 decimal. |
| `humidity` | `HumiditySensor.read().value` | Porcentaje, 1 decimal. |
| `energy` | `EnergyStatusSensor.read().value` | `on` o `off`, valores de `EnergyState` en minúsculas. |
| `timestamp` | ISO 8601, precisión de segundos | Momento de generación del payload del ciclo. |
