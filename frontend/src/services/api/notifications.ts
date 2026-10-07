// Servicio de dominio: notificaciones y reconocimiento de alertas (TSK-050).
//
// Contratos reales (backend/app/notifications/api/router.py):
// - GET /notifications/history?limit&status&channel&alert_id
//     → {count, notifications[{id,alert_id,channel,status,notification_date,alert?}]}
//     (canal: dashboard|email|sms|push; estado: pending|sent|failed; Bearer)
// - POST /notifications/alerts/{alert_id}/acknowledge
//     → {message, alert_id, acknowledged, alert{...}}
//     Body opcional (user_id ignorado: el actor sale del token). Roles:
//     admin, supervisor, operador (require_ack). 404 si la alerta no está en
//     la sesión runtime del backend aunque exista su fila persistida.

import { apiFetch } from './client';

export type NotificationChannel = 'dashboard' | 'email' | 'sms' | 'push';
export type NotificationStatus = 'pending' | 'sent' | 'failed';

export interface NotificationAlertSummary {
  id: string;
  device_id: string;
  user_id: string;
  type: string;
  message: string;
  criticality: number;
  acknowledged: boolean;
  created_at: string;
}

export interface NotificationRecord {
  id: string;
  alert_id: string;
  channel: string;
  status: string;
  notification_date: string;
  alert?: NotificationAlertSummary;
}

export interface NotificationHistoryResponse {
  count: number;
  notifications: NotificationRecord[];
}

export async function apiGetNotificationHistory(params?: { limit?: number }): Promise<NotificationHistoryResponse> {
  const qs = new URLSearchParams();
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  const suffix = qs.toString();
  return apiFetch<NotificationHistoryResponse>(`/notifications/history${suffix ? `?${suffix}` : ''}`);
}

export interface AcknowledgeAlertResponse {
  message: string;
  alert_id: string;
  acknowledged: boolean;
  alert: NotificationAlertSummary;
}

export async function apiAcknowledgeAlert(alertId: string): Promise<AcknowledgeAlertResponse> {
  return apiFetch<AcknowledgeAlertResponse>(
    `/notifications/alerts/${encodeURIComponent(alertId)}/acknowledge`,
    { method: 'POST' },
  );
}
