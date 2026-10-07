// Servicio de dominio: alertas (TSK-048/TSK-050).
//
// Fuente principal: GET /history/alerts (AlertHistoryRepository, persistido).
// Parámetros reales: device_code, type, acknowledged, from_ts, to_ts,
// sort, page, per_page. Los endpoints /events/* en memoria no se usan como
// fuente del Dashboard; la vista de alertas los consume vía services/api/events.ts.

import { apiFetch } from './client';
import type { HistoryAlertListResponse } from './history';

export interface AlertsQuery {
  page?: number;
  per_page?: number;
  sort?: string;
  type?: string;
  acknowledged?: boolean;
}

export async function apiGetAlerts(params?: AlertsQuery): Promise<HistoryAlertListResponse> {
  const qs = new URLSearchParams();
  qs.set('page', String(params?.page ?? 1));
  qs.set('per_page', String(params?.per_page ?? 20));
  qs.set('sort', params?.sort ?? 'created_at.desc');
  if (params?.type) qs.set('type', params.type);
  if (params?.acknowledged !== undefined) qs.set('acknowledged', String(params.acknowledged));
  return apiFetch<HistoryAlertListResponse>(`/history/alerts?${qs.toString()}`);
}
