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

// ─── Colas en vivo (volátiles; no pertenecen a ninguna ejecución) ───────────
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
