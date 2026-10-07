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
