import { apiFetch } from './client';

export async function apiGetAuditLogs() {
  // Previamente: GET /audit-logs
  return apiFetch('/audit-logs');
}
