// Servicio de dominio: eventos de sesión / runtime (TSK-050).
//
// Contratos reales (backend/app/events/api/__init__.py):
// - GET /events/alerts?limit            → {count, alerts[]}      (sesión actual)
// - GET /events/alerts/critical?limit  → {count, alerts[]}      (criticality >= 7, sesión)
// - GET /events/events?limit           → {count, events[]}      (eventos detectados, sesión)
// - GET /events/summary                → {total_alerts, total_events, acknowledged_alerts,
//                                         unacknowledged_alerts, alert_types, event_types}
// Todo vive en app.state del backend: representa la SESIÓN actual, no el
// historial persistido (ese es GET /history/alerts). Requiere Bearer.

import { apiFetch } from './client';

export interface SessionAlert {
  id: string;
  device_id: string;
  user_id: string;
  type: string;
  message: string;
  criticality: number;
  acknowledged: boolean;
  created_at: string;
}

export interface SessionAlertListResponse {
  count: number;
  alerts: SessionAlert[];
}

export async function apiGetSessionAlerts(limit?: number): Promise<SessionAlertListResponse> {
  const qs = new URLSearchParams();
  if (limit !== undefined) qs.set('limit', String(limit));
  const suffix = qs.toString();
  return apiFetch<SessionAlertListResponse>(`/events/alerts${suffix ? `?${suffix}` : ''}`);
}

export async function apiGetCriticalAlerts(limit?: number): Promise<SessionAlertListResponse> {
  const qs = new URLSearchParams();
  if (limit !== undefined) qs.set('limit', String(limit));
  const suffix = qs.toString();
  return apiFetch<SessionAlertListResponse>(`/events/alerts/critical${suffix ? `?${suffix}` : ''}`);
}

export interface SessionEvent {
  id: string;
  device_code: string;
  variable: string;
  event_type: string;
  message: string;
  observed_value: number | string;
  threshold?: number | string;
  detected_at: string;
}

export interface SessionEventListResponse {
  count: number;
  events: SessionEvent[];
}

export async function apiGetSessionEvents(limit?: number): Promise<SessionEventListResponse> {
  const qs = new URLSearchParams();
  if (limit !== undefined) qs.set('limit', String(limit));
  const suffix = qs.toString();
  return apiFetch<SessionEventListResponse>(`/events/events${suffix ? `?${suffix}` : ''}`);
}

export interface EventsSummary {
  total_alerts: number;
  total_events: number;
  acknowledged_alerts: number;
  unacknowledged_alerts: number;
  alert_types: Record<string, number>;
  event_types: Record<string, number>;
}

export async function apiGetEventsSummary(): Promise<EventsSummary> {
  return apiFetch<EventsSummary>('/events/summary');
}
