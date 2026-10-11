// Servicio de dominio: notificaciones y reconocimiento de alertas (TSK-050 + Fase C).
//
// Contratos reales (backend/app/notifications/api/router.py):
// - GET /notifications/history?limit&status&channel&alert_id (runtime volátil,
//   prototipo sin cambios; canal: dashboard|email|sms|push;
//   estado: pending|sent|failed|simulated|disabled; Bearer)
// - GET /notifications/persistent?limit&status&channel&alert_id&is_read
//     → {count, notifications[{id,alert_id,channel,status,notification_date,
//        is_read,read_at,alert?}]} — historial durable, SOLO filas propias
//     (user_id del token). Límite por defecto 50, máximo 200.
// - GET /notifications/unread-count → {unread} (filas propias no leídas).
// - PATCH /notifications/{id}/read → {message, notification} (solo propia;
//   404 si no existe o es de otro usuario; idempotente).
// - POST /notifications/read-all → {updated} (solo propias).
// - POST /notifications/alerts/{alert_id}/acknowledge
//     → {message, alert_id, acknowledged, alert{...}}
//     Body opcional (user_id ignorado: el actor sale del token). Roles:
//     admin, supervisor, operador (require_ack). 404 si la alerta no está en
//     la sesión runtime del backend aunque exista su fila persistida.
// Lectura (is_read) y reconocimiento (acknowledged) son independientes en
// ambas direcciones: ninguna acción toca el otro estado.

import { apiFetch } from './client';

export type NotificationChannel = 'dashboard' | 'email' | 'sms' | 'push';
export type NotificationStatus = 'pending' | 'sent' | 'failed' | 'simulated' | 'disabled';

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
  /** Solo presente en el historial persistente (fase C). */
  is_read?: boolean;
  /** ISO o null; solo historial persistente. */
  read_at?: string | null;
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

export interface PersistentHistoryParams {
  limit?: number;
  status?: string;
  channel?: string;
  alert_id?: string;
  /** 'true' | 'false' (el backend valida el literal). */
  is_read?: 'true' | 'false';
}

/** Historial durable del usuario autenticado (fase C). Sin polling propio:
// los hooks llaman una vez por ciclo de su propio polling existente. */
export async function apiGetPersistentHistory(params?: PersistentHistoryParams): Promise<NotificationHistoryResponse> {
  const qs = new URLSearchParams();
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  if (params?.status !== undefined) qs.set('status', params.status);
  if (params?.channel !== undefined) qs.set('channel', params.channel);
  if (params?.alert_id !== undefined) qs.set('alert_id', params.alert_id);
  if (params?.is_read !== undefined) qs.set('is_read', params.is_read);
  const suffix = qs.toString();
  return apiFetch<NotificationHistoryResponse>(`/notifications/persistent${suffix ? `?${suffix}` : ''}`);
}

export interface UnreadCountResponse {
  unread: number;
}

/** Contador ligero para la campana (fase C). Respuesta mínima, sin listas. */
export async function apiGetUnreadCount(): Promise<UnreadCountResponse> {
  return apiFetch<UnreadCountResponse>('/notifications/unread-count');
}

export interface MarkReadResponse {
  message: string;
  notification: NotificationRecord;
}

export async function apiMarkNotificationRead(notificationId: string): Promise<MarkReadResponse> {
  return apiFetch<MarkReadResponse>(
    `/notifications/${encodeURIComponent(notificationId)}/read`,
    { method: 'PATCH' },
  );
}

export interface MarkAllReadResponse {
  updated: number;
}

export async function apiMarkAllNotificationsRead(): Promise<MarkAllReadResponse> {
  return apiFetch<MarkAllReadResponse>('/notifications/read-all', { method: 'POST' });
}

/** Evento local para refresco inmediato del contador tras marcar lecturas
 * (evita acortar el polling o duplicar consultas). */
export const NOTIFICATIONS_CHANGED_EVENT = 'coldchain:notifications-changed';

export function notifyNotificationsChanged(): void {
  if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
    window.dispatchEvent(new CustomEvent(NOTIFICATIONS_CHANGED_EVENT));
  }
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
