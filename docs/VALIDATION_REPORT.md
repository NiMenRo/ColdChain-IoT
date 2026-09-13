# Validation Report – TSK API REST + History

## Entorno
- **Backend:** FastAPI 0.141, Uvicorn, SQLAlchemy 2.0.52 (Uuid generic), psycopg 3.2, Alembic 1.13, Python 3.10
- **DB:** PostgreSQL 16-alpine `coldchain:coldchain@localhost:5433/coldchain` (Docker, volumen `postgres_data`), SQLite `:memory:` con `StaticPool` + `PRAGMA foreign_keys=ON` para unit tests
- **Migraciones:** `cff6c25b6661_initial_schema` (8 tablas) + `7b7ca6d02489_sensor_reading_energy_string` (Boolean→VARCHAR)
- **Seed:** `CAVA-001` (cold_room active), `CAVA-002` (maintenance), `VITRINA-001` (refrigerated_showcase active) + `system` user `00000000-0000-0000-0000-000000000000`

## Datos de prueba
- **Persistencia atómica:** `SensorReading(energy String on/off/intermittent) 1:1 TrafficClassification UNIQUE reading_id 1:N QoSMetric, Alert FK Device/User, Prediction 1:N`
- **Simulación:** 3 ciclos × 3 dispositivos = 9 mensajes → 9 `sensor_readings`, 9 `traffic_classifications`, 9 `qos_metrics`, 15 `alerts`, 0 `predictions` (vacío válido, sin datos simulados)
- **Bundle:** `Device → SensorReading → TC → QoSMetric → Alerts` con `TC.reading_id = SR.id`, `QM.classification_id = TC.id`, `Alert.device_id = SR.device_id` (remap), `energy` preservado

## Pruebas unitarias (SQLite :memory:)
- `app/history/tests/test_history_api.py` (8 tests): paginación, filtro `device_code`, `priority`, `type`, `acknowledged`, orden `timestamp.desc`, `404` en `GET /{id}`, `400` per_page>100, `trends` (avg/min/max), `bundle`, `summary`, `predictions` vacío, `device/history` 404, relaciones sin duplicados 1:N
- `app/database/tests/test_persistence_service.py` (1 test): atomicidad `SensorReading→TC→QoS→Alert` con `begin_nested`, FK `Device/User`, rollback en `IntegrityError`, 1:1 `TC.reading_id` UNIQUE, `energy` String
- **Resultado:** 9 passed, 5 warnings (Pydantic V1 validators)

## Pruebas de integración (Postgres 5433 real)
- **Flujo:** `coldchain.ps1 start` → 1 ciclo simulador → `persist_bundle` con `qos_metric=build_metric(record, classification_id=TC.id)` (reemplaza, no duplica `MessageDeliveryRecord`)
- **Verificación:** `docker exec psql -c "SELECT count(*) FROM sensor_readings"` → 9, `traffic_classifications` 9, `qos_metrics` 9 (1:1 por TC), `alerts` 15
- **API vs DB:** `GET /history/summary` (`total_readings 9` etc.) coincide con `SELECT count(*)`; `GET /history/readings?device_code=CAVA-001` → 3, `GET /history/readings?device_code=NOEXISTE` → 200 `{total 0, results []}`; `GET /history/readings/{uuid}` inexistente → 404
- **Tendencias:** `GET /history/readings/trends?interval=hour` y `GET /history/qos/trends?interval=hour` → 200 con `avg/min/max`
- **Predicciones:** `GET /history/predictions` → 200 `{total 0, results []}` vacío válido, sin `RandomForest`/`sklearn`

## Conteos PostgreSQL vs API (tras 3 ciclos)
| Tabla | COUNT | API `total` |
|-------|-------|-------------|
| `devices` | 3 | `GET /history/devices` → 3 |
| `sensor_readings` | 9 | `GET /history/readings` → 9 |
| `traffic_classifications` | 9 | `GET /history/classifications` → 9 |
| `qos_metrics` | 9 | `GET /history/qos` → 9 |
| `alerts` | 15 | `GET /history/alerts` → 15 |
| `predictions` | 0 | `GET /history/predictions` → 0 |

## Validación de relaciones
- `sr.device_id = d.id` (FK `devices`), `tc.reading_id = sr.id` (UNIQUE 1:1), `qm.classification_id = tc.id` (1:N sin duplicados), `a.device_id = sr.device_id` (remap)
- `JOIN` `sr→tc→qm` sin duplicados: `SELECT tc.reading_id = sr.id` → `t`

## Endpoints validados
- `GET /history/readings`, `/{id}`, `/{id}/bundle`, `/trends`
- `GET /history/classifications`, `/{id}`
- `GET /history/qos`, `/{id}`, `/trends`
- `GET /history/alerts`, `/{id}`
- `GET /history/predictions`, `/{id}` (vacío)
- `GET /history/devices`, `/{code}/history`
- `GET /history/summary`

## Conclusiones
Capa REST histórica completa sobre datos reales, paginada, filtrable, ordenable, agregable para dashboard, sin recalcular QoS, sin tabla `EnrichedEvent`, sin tocar `/events/*`, frontend pendiente.

## Limitaciones actuales
- `predictions` requiere productor real (RandomForest) – vacía.
- `SystemConfig` sin histórico.
- `trends` solo `hour/minute/day` via `date_trunc`/`strftime`.
