// Servicio de dominio: métricas QoS de sesión / runtime (TSK-050).
//
// Contrato real (backend/app/qos/api/__init__.py):
// - GET /qos/metrics → {count, summary{latency,jitter,throughput,pdr,packet_loss},
//                        by_priority} (Bearer)
// Sin registros en la sesión, summary trae ceros y by_priority {}. El
// histórico persistido vive en GET /history/qos (services/api/history.ts)
// y queda para análisis posterior (TSK-052).

import { apiFetch } from './client';

export interface QosSessionSummary {
  latency: number;
  jitter: number;
  throughput: number;
  pdr: number;
  packet_loss: number;
}

export interface QosMetricsResponse {
  count: number;
  summary: QosSessionSummary;
  by_priority: Record<string, QosSessionSummary>;
}

export async function apiGetQosMetrics(): Promise<QosMetricsResponse> {
  return apiFetch<QosMetricsResponse>('/qos/metrics');
}

// ─── Colas de demostración (volátiles; no son el despacho productivo) ──────
// Contrato real (backend/app/qos/api/__init__.py get_queues): snapshot del
// contenido actual de los schedulers en memoria {count, queues{low,medium,
// high[]}}. Se vacía al reiniciar el backend. Sin filtro run_id posible.

export interface LiveQueueItem {
  id: string;
  reading_id: string;
  criticality: number;
  priority: string;
  queue: string;
  timestamp: string;
}

export interface LiveQueuesResponse {
  count: number;
  queues: Record<'low' | 'medium' | 'high', LiveQueueItem[]>;
}

export async function apiGetLiveQueues(): Promise<LiveQueuesResponse> {
  return apiFetch<LiveQueuesResponse>('/qos/queues');
}

// ─── Runtime productivo del despacho (GET /qos/runtime) ─────────────────────
// Contrato real (backend/app/qos/api/__init__.py get_runtime): estado vivo del
// coordinador que admite y atiende lecturas. Es distinto de /qos/queues (que
// sigue mostrando el planner de demostración). 409 = despacho no activo.
// `transport` puede ser null si el backend no expone la cola MQTT; `config`
// puede ser null sin BackendConfig cargado. Los campos de transporte son
// nullable: se muestran como «—», nunca como cero inventado.

export type QosClass = 'high' | 'medium' | 'low';

export interface QosDispatchSnapshot {
  admitted: number;
  rejected: number;
  completed: number;
  failed: number;
  pending: number;
  in_flight: number;
  capacity: number;
  closed: boolean;
  draining: boolean;
  draining_run_id: string | null;
  without_qos_pending: number;
  queues: Partial<Record<QosClass, number>>;
  pending_sample?: Partial<Record<QosClass | 'without_qos', QosPendingItem[]>>;
}

export interface QosPendingItem {
  work_id: string;
  source_message_id: string;
  device_code: string;
  sensor_name: string;
  sequence: number;
  scenario: 'WITH_QOS' | 'WITHOUT_QOS';
  priority: QosClass | null;
  run_id: string | null;
  admitted_at: string;
}

export interface QosTransportSnapshot {
  pending: number | null;
  capacity: number | null;
  rejected: number | null;
}

export interface QosEffectiveConfig {
  class_quotas?: Partial<Record<QosClass, number>>;
  wfq_flow_weights?: Record<string, number>;
  capacities?: {
    transport_messages?: number;
    pending_work_items?: number;
    recent_trace_entries?: number;
    recent_failure_entries?: number;
  };
  timeouts?: { drain_s?: number };
}

export interface QosRuntimeResponse {
  dispatch: QosDispatchSnapshot;
  transport: QosTransportSnapshot | null;
  config: QosEffectiveConfig | null;
}

export async function apiGetQosRuntime(): Promise<QosRuntimeResponse> {
  return apiFetch<QosRuntimeResponse>('/qos/runtime');
}
