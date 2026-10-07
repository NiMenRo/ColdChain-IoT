// Servicio de dominio: histórico persistido del backend (TSK-048/TSK-049).
//
// Fuente principal del Dashboard y de dispositivos/lecturas. Contratos reales:
// - GET /history/summary            (HistoryService.summary)
// - GET /history/alerts             (AlertHistoryRepository.list)
// - GET /history/readings           (ReadingHistoryRepository.list)
// - GET /history/readings/trends    (ReadingHistoryRepository.trends)
// - GET /history/qos/trends         (QoSHistoryRepository.trends)
// - GET /history/classifications    (ClassificationHistoryRepository.list)
// - GET /history/devices/{code}/history (DeviceHistoryRepository.history)
// Todos exigen autenticación Bearer en el backend.

import { apiFetch } from './client';

// ─── Resumen agregado por el backend (sin agregación en frontend) ────────────

export interface HistorySummary {
  total_devices: number;
  total_readings: number;
  total_classifications: number;
  total_qos_metrics: number;
  total_alerts: number;
  total_predictions: number;
  alerts_by_type: Record<string, number>;
  readings_by_device: Record<string, number>;
  /** Claves en minúsculas según CHECK: 'low' | 'medium' | 'high'. */
  traffic_by_priority: Record<string, number>;
  qos_by_queue: Record<string, number>;
}

export async function apiGetHistorySummary(): Promise<HistorySummary> {
  return apiFetch<HistorySummary>('/history/summary');
}

// ─── Alertas persistidas ─────────────────────────────────────────────────────

export interface HistoryAlert {
  id: string;
  device_id: string;
  user_id: string;
  type: string;
  message: string;
  criticality: number;
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
}

export async function apiGetHistoryAlerts(params?: HistoryAlertsParams): Promise<HistoryAlertListResponse> {
  const qs = new URLSearchParams();
  qs.set('page', String(params?.page ?? 1));
  qs.set('per_page', String(params?.per_page ?? 5));
  qs.set('sort', params?.sort ?? 'created_at.desc');
  if (params?.acknowledged !== undefined) qs.set('acknowledged', String(params.acknowledged));
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
  params?: { device_code?: string },
): Promise<ReadingTrendPoint[]> {
  const qs = new URLSearchParams();
  if (params?.device_code) qs.set('device_code', params.device_code);
  qs.set('interval', interval);
  return apiFetch<ReadingTrendPoint[]>(`/history/readings/trends?${qs.toString()}`);
}

// ─── Lecturas crudas (ordenadas por el backend; sin agregación en frontend) ──

export interface HistoryReading {
  id: string;
  device_id: string;
  temperature: number | null;
  humidity: number | null;
  /** 'on' | 'off' | null (NULL = sensor no habilitado). Nunca se deriva de status. */
  energy: 'on' | 'off' | null;
  timestamp: string;
  run_id: string | null;
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
}): Promise<HistoryReadingListResponse> {
  const qs = new URLSearchParams();
  if (params?.device_code) qs.set('device_code', params.device_code);
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

// ─── Tendencias QoS (promedios calculados por el backend) ────────────────────

export interface QosTrendPoint {
  bucket: string;
  avg_latency: number;
  min_latency: number;
  max_latency: number;
  avg_packet_loss: number;
  avg_throughput: number;
  avg_pdr: number;
  avg_jitter: number;
}

export async function apiGetQosTrends(interval: HistoryInterval = 'hour'): Promise<QosTrendPoint[]> {
  return apiFetch<QosTrendPoint[]>(`/history/qos/trends?interval=${interval}`);
}

// ─── Métricas QoS persistidas (listado crudo; agregados → TSK-052) ──────────

export interface QosRecord {
  id: string;
  classification_id: string;
  latency: number;
  packet_loss: number;
  throughput: number;
  pdr: number;
  jitter: number;
  timestamp: string;
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
}): Promise<QosRecordListResponse> {
  const qs = new URLSearchParams();
  qs.set('sort', params?.sort ?? 'timestamp.desc');
  qs.set('page', String(params?.page ?? 1));
  qs.set('per_page', String(params?.per_page ?? 5));
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

export async function apiGetClassifications(params?: { page?: number; per_page?: number }): Promise<HistoryClassificationListResponse> {
  const qs = new URLSearchParams();
  qs.set('page', String(params?.page ?? 1));
  qs.set('per_page', String(params?.per_page ?? 20));
  return apiFetch<HistoryClassificationListResponse>(`/history/classifications?${qs.toString()}`);
}
