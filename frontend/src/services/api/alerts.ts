// Servicio de dominio: alertas recientes del Dashboard (TSK-048).
//
// Fuente principal: GET /history/alerts (AlertHistoryRepository, persistido).
// Los endpoints /events/* en memoria no se usan como fuente del Dashboard.

import { apiFetch } from './client';
import type { HistoryAlertListResponse } from './history';

export async function apiGetAlerts(params?: { page?: number; per_page?: number }): Promise<HistoryAlertListResponse> {
  const qs = new URLSearchParams();
  qs.set('page', String(params?.page ?? 1));
  qs.set('per_page', String(params?.per_page ?? 5));
  qs.set('sort', 'created_at.desc');
  return apiFetch<HistoryAlertListResponse>(`/history/alerts?${qs.toString()}`);
}
