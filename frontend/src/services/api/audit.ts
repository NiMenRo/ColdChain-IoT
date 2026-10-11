// Servicio de dominio: auditoría (solo lectura).
//
// Contrato real (backend/app/audit/api.py + schemas.py):
// - GET /audit-logs?page&per_page → {total,page,per_page,count,
//     results[{id,actor_user_id,action,resource,outcome,old_value,new_value,created_at}]}
// Solo admin/auditor (403 en otro caso). Sin filtros server-side: la vista
// filtra sobre la página traída.

import { apiFetch } from './client';

export interface AuditLogRecord {
  id: string;
  actor_user_id: string;
  action: string;
  resource: string;
  outcome: string;
  old_value: string | null;
  new_value: string | null;
  created_at: string;
}

export interface AuditLogListResponse {
  total: number;
  page: number;
  per_page: number;
  count: number;
  results: AuditLogRecord[];
}

export async function apiGetAuditLogs(params?: { page?: number; per_page?: number }): Promise<AuditLogListResponse> {
  const qs = new URLSearchParams();
  qs.set('page', String(params?.page ?? 1));
  qs.set('per_page', String(params?.per_page ?? 20));
  return apiFetch<AuditLogListResponse>(`/audit-logs?${qs.toString()}`);
}
