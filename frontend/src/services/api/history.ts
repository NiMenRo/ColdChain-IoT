// Servicio de dominio: histórico persistido del backend (TSK-048/TSK-049/TSK-052).
//
// Fuente principal del Dashboard, dispositivos/lecturas y análisis histórico.
// Contratos reales (backend/app/history/api/router.py):
// - GET /history/summary            (HistoryService.summary)
// - GET /history/alerts             (AlertHistoryRepository.list)
// - GET /history/readings           (ReadingHistoryRepository.list)
// - GET /history/readings/trends    (ReadingHistoryRepository.trends)
// - GET /history/qos/trends         (QoSHistoryRepository.trends)
// - GET /history/classifications    (ClassificationHistoryRepository.list)
// - GET /history/devices/{code}/history (DeviceHistoryRepository.history)
// Todos exigen autenticación Bearer en el backend. Los filtros temporales
// (from_ts/to_ts) y por ejecución (run_id, resuelto por el backend vía
// SensorReading.run_id / Alert.run_id) los ejecuta el backend; el frontend
// nunca simula filtrado. Sin run_id: ámbito global (incluye legado NULL).

import { apiFetch } from './client';

// ─── Resumen agregado por el backend (sin agregación en frontend) ────────────

export interface HistorySummary {
  total_devices: number;
  active_devices: number;
  error_devices: number;
  total_readings: number;
  total_classifications: number;
  total_qos_metrics: number;
  total_alerts: number;
  active_alerts: number;
  critical_active_alerts: number;
  total_predictions: number;
  alerts_by_type: Record<string, number>;
  readings_by_device: Record<string, number>;
  /** Claves en minúsculas según CHECK: 'low' | 'medium' | 'high'. */
  traffic_by_priority: Record<string, number>;
  qos_by_queue: Record<string, number>;
  /** Conteo de lecturas por estado energético ('on'/'off', nulos excluidos). */
  energy_by_state?: Record<string, number>;
  /** Conteo de alertas sin criticidad calculada (p. ej. ejecuciones sin QoS). */
  alerts_without_criticality?: number;
  /** Eco del filtro aplicado; null = ámbito global. */
  run_id?: string | null;
}

export async function apiGetHistorySummary(params?: { run_id?: string }): Promise<HistorySummary> {
  const qs = new URLSearchParams();
  if (params?.run_id) qs.set('run_id', params.run_id);
  const suffix = qs.toString();
  return apiFetch<HistorySummary>(`/history/summary${suffix ? `?${suffix}` : ''}`);
}

// ─── Alertas persistidas ─────────────────────────────────────────────────────

export interface HistoryAlert {
  id: string;
  device_id: string;
  user_id: string;
  type: string;
  message: string;
  criticality: number | null;
  acknowledged: boolean;
  created_at: string;
  run_id: string | null;
}

export interface HistoryAlertListResponse {
  total: number;
  page: number;
  per_page: number;
  count: number;
  results: HistoryAlert[];
}

export interface HistoryAlertsParams {
  page?: number;
  per_page?: number;
  sort?: string;
  acknowledged?: boolean;
  type?: string;
  from_ts?: string;
  to_ts?: string;
  run_id?: string;
}

export async function apiGetHistoryAlerts(params?: HistoryAlertsParams): Promise<HistoryAlertListResponse> {
  const qs = new URLSearchParams();
  qs.set('page', String(params?.page ?? 1));
  qs.set('per_page', String(params?.per_page ?? 5));
  qs.set('sort', params?.sort ?? 'created_at.desc');
  if (params?.acknowledged !== undefined) qs.set('acknowledged', String(params.acknowledged));
  if (params?.type) qs.set('type', params.type);
  if (params?.from_ts) qs.set('from_ts', params.from_ts);
  if (params?.to_ts) qs.set('to_ts', params.to_ts);
  if (params?.run_id) qs.set('run_id', params.run_id);
  return apiFetch<HistoryAlertListResponse>(`/history/alerts?${qs.toString()}`);
}

// ─── Tendencias de lecturas (promedios calculados por el backend) ────────────

export type HistoryInterval = 'minute' | 'hour' | 'day';

export interface ReadingTrendPoint {
  bucket: string;
  avg_temp: number | null;
  min_temp: number | null;
  max_temp: number | null;
  avg_hum: number | null;
  min_hum: number | null;
  max_hum: number | null;
}

export async function apiGetReadingTrends(
  interval: HistoryInterval = 'hour',
  params?: { device_code?: string; from_ts?: string; to_ts?: string; run_id?: string },
): Promise<ReadingTrendPoint[]> {
  const qs = new URLSearchParams();
  if (params?.device_code) qs.set('device_code', params.device_code);
  if (params?.from_ts) qs.set('from_ts', params.from_ts);
  if (params?.to_ts) qs.set('to_ts', params.to_ts);
  if (params?.run_id) qs.set('run_id', params.run_id);
  qs.set('interval', interval);
  return apiFetch<ReadingTrendPoint[]>(`/history/readings/trends?${qs.toString()}`);
}

// ─── Lecturas crudas (ordenadas por el backend; sin agregación en frontend) ──

export interface HistoryReading {
  id: string;
  device_id: string;
  temperature: number | null;
  humidity: number | null;
  /** NULL = sin valor en esta fila (también sensores hermanos en v2), no sensor deshabilitado. */
  energy: 'on' | 'off' | null;
  timestamp: string;
  run_id: string | null;
  processing_version: 1 | 2;
  source_message_id: string | null;
  sensor_name: 'temperature' | 'humidity' | 'energy' | null;
}

export interface HistoryReadingListResponse {
  total: number;
  page: number;
  per_page: number;
  count: number;
  results: HistoryReading[];
}

export async function apiGetReadings(params?: {
  device_code?: string;
  sort?: string;
  page?: number;
  per_page?: number;
  run_id?: string;
  processing_version?: 1 | 2;
}): Promise<HistoryReadingListResponse> {
  const qs = new URLSearchParams();
  if (params?.device_code) qs.set('device_code', params.device_code);
  if (params?.run_id) qs.set('run_id', params.run_id);
  if (params?.processing_version) qs.set('processing_version', String(params.processing_version));
  qs.set('sort', params?.sort ?? 'timestamp.desc');
  qs.set('page', String(params?.page ?? 1));
  qs.set('per_page', String(params?.per_page ?? 20));
  return apiFetch<HistoryReadingListResponse>(`/history/readings?${qs.toString()}`);
}

// ─── Historial por dispositivo (device + lecturas en una llamada) ────────────

export interface DeviceHistoryResponse {
  device: {
    id: string;
    code: string;
    name: string;
    location: string;
    device_type: string;
    status: string;
    registration_date: string;
  };
  total: number;
  page: number;
  per_page: number;
  count: number;
  results: HistoryReading[];
}

export async function apiGetDeviceHistory(
  deviceCode: string,
  params?: { page?: number; per_page?: number },
): Promise<DeviceHistoryResponse> {
  const qs = new URLSearchParams();
  qs.set('page', String(params?.page ?? 1));
  qs.set('per_page', String(params?.per_page ?? 5));
  return apiFetch<DeviceHistoryResponse>(`/history/devices/${encodeURIComponent(deviceCode)}/history?${qs.toString()}`);
}

export type DeviceLatestValues = Record<'temperature' | 'humidity' | 'energy', HistoryReading | null>;

/** Última fila no NULL por sensor, sin limitarse a la página de historial. */
export async function apiGetDeviceLatestValues(deviceCode: string): Promise<DeviceLatestValues> {
  return apiFetch<DeviceLatestValues>(`/history/devices/${encodeURIComponent(deviceCode)}/latest-values`);
}

// ─── Tendencias QoS (promedios calculados por el backend) ────────────────────
// v2 permite métricas no medibles: avg sobre un bucket con todos los valores
// NULL devuelve NULL. El consumidor debe tratar null como «no disponible»,
// nunca multiplicarlo/convertirlo en 0.

export interface QosTrendPoint {
  bucket: string;
  avg_latency: number | null;
  min_latency: number | null;
  max_latency: number | null;
  avg_packet_loss: number | null;
  avg_throughput: number | null;
  avg_pdr: number | null;
  avg_jitter: number | null;
}

export async function apiGetQosTrends(
  interval: HistoryInterval = 'hour',
  params?: { device_code?: string; from_ts?: string; to_ts?: string; run_id?: string },
): Promise<QosTrendPoint[]> {
  const qs = new URLSearchParams();
  if (params?.device_code) qs.set('device_code', params.device_code);
  if (params?.from_ts) qs.set('from_ts', params.from_ts);
  if (params?.to_ts) qs.set('to_ts', params.to_ts);
  if (params?.run_id) qs.set('run_id', params.run_id);
  qs.set('interval', interval);
  return apiFetch<QosTrendPoint[]>(`/history/qos/trends?${qs.toString()}`);
}

// ─── Métricas QoS persistidas (listado crudo; agregados → TSK-052) ──────────
// Desde el esquema v2 las métricas de calidad pueden ser NULL (no medibles) y
// se añaden marcas temporales y duraciones de despacho. `processing_version=1`
// identifica filas legadas; en ellas los campos de despacho son NULL.

export interface QosRecord {
  id: string;
  classification_id: string;
  latency: number | null;
  packet_loss: number | null;
  throughput: number | null;
  pdr: number | null;
  jitter: number | null;
  timestamp: string;
  processing_version?: number;
  selected_at?: string | null;
  persisted_at?: string | null;
  finished_at?: string | null;
  queue_wait_ms?: number | null;
  service_time_ms?: number | null;
}

export interface QosRecordListResponse {
  total: number;
  page: number;
  per_page: number;
  count: number;
  results: QosRecord[];
}

export async function apiGetQosRecords(params?: {
  sort?: string;
  page?: number;
  per_page?: number;
  device_code?: string;
  from_ts?: string;
  to_ts?: string;
  run_id?: string;
}): Promise<QosRecordListResponse> {
  const qs = new URLSearchParams();
  qs.set('sort', params?.sort ?? 'timestamp.desc');
  qs.set('page', String(params?.page ?? 1));
  qs.set('per_page', String(params?.per_page ?? 5));
  if (params?.device_code) qs.set('device_code', params.device_code);
  if (params?.from_ts) qs.set('from_ts', params.from_ts);
  if (params?.to_ts) qs.set('to_ts', params.to_ts);
  if (params?.run_id) qs.set('run_id', params.run_id);
  return apiFetch<QosRecordListResponse>(`/history/qos?${qs.toString()}`);
}

// ─── Clasificaciones persistidas ─────────────────────────────────────────────

export interface HistoryClassification {
  id: string;
  reading_id: string;
  criticality: number;
  /** 'low' | 'medium' | 'high' según CHECK del backend. */
  priority: string;
  /** 'FIFO' | 'Round Robin' | 'WFQ' según CHECK del backend. */
  queue: string;
  classification_time: string;
  timestamp: string;
}

export interface HistoryClassificationListResponse {
  total: number;
  page: number;
  per_page: number;
  count: number;
  results: HistoryClassification[];
}

export async function apiGetClassifications(params?: {
  page?: number;
  per_page?: number;
  sort?: string;
  priority?: string;
  queue?: string;
  from_ts?: string;
  to_ts?: string;
  run_id?: string;
}): Promise<HistoryClassificationListResponse> {
  const qs = new URLSearchParams();
  qs.set('page', String(params?.page ?? 1));
  qs.set('per_page', String(params?.per_page ?? 20));
  qs.set('sort', params?.sort ?? 'timestamp.desc');
  if (params?.priority) qs.set('priority', params.priority);
  if (params?.queue) qs.set('queue', params.queue);
  if (params?.from_ts) qs.set('from_ts', params.from_ts);
  if (params?.to_ts) qs.set('to_ts', params.to_ts);
  if (params?.run_id) qs.set('run_id', params.run_id);
  return apiFetch<HistoryClassificationListResponse>(`/history/classifications?${qs.toString()}`);
}
