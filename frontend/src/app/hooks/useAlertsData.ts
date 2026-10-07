// Hook de alertas, eventos de sesión y notificaciones (TSK-050).
//
// Patrón: AlertsView → useAlertsData → services/api/* → apiFetch → Backend.
// - Historial persistido: GET /history/alerts (filtro `type` server-side).
// - Sesión runtime: GET /events/summary, /events/alerts/critical, /events/events.
// - Notificaciones: GET /notifications/history.
// - Reconocimiento: POST /notifications/alerts/{id}/acknowledge + refetch.
// Una sola carga al montar (+ refetch manual). Sin polling ni realtime.

import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../../services/api/client';
import { apiGetAlerts } from '../../services/api/alerts';
import { apiGetDevices } from '../../services/api/devices';
import {
  apiGetCriticalAlerts,
  apiGetEventsSummary,
  apiGetSessionEvents,
  type SessionEvent,
  type SessionAlert,
  type EventsSummary,
} from '../../services/api/events';
import {
  apiAcknowledgeAlert,
  apiGetNotificationHistory,
  type NotificationRecord,
} from '../../services/api/notifications';
import type { Device } from '../types/devices';

export type SectionStatus = 'loading' | 'success' | 'empty' | 'error';

// Tipos exactos del backend (app/events/domain). El cuarto es HUMIDITY_BELOW_MIN.
export const ALERT_TYPES = [
  'TEMPERATURE_EXCEEDED',
  'TEMPERATURE_BELOW_MIN',
  'HUMIDITY_ABOVE_MAX',
  'HUMIDITY_BELOW_MIN',
  'ENERGY_STATE_ANOMALY',
] as const;

export type AlertFilter = 'all' | (typeof ALERT_TYPES)[number];

const ALERT_TYPE_LABEL: Record<string, string> = {
  TEMPERATURE_EXCEEDED: 'Temperatura Excedida',
  TEMPERATURE_BELOW_MIN: 'Temperatura Bajo Mínimo',
  HUMIDITY_ABOVE_MAX: 'Humedad sobre Máximo',
  HUMIDITY_BELOW_MIN: 'Humedad bajo Mínimo',
  ENERGY_STATE_ANOMALY: 'Anomalía de Estado Energético',
};

export function alertLabel(type: string): string {
  return ALERT_TYPE_LABEL[type] ?? type;
}

export interface AlertItem {
  id: string;
  type: string;
  label: string;
  message: string;
  deviceId: string;
  deviceName: string;
  criticality: number;
  timestamp: string;
  acknowledged: boolean;
}

export function formatTs(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('es-CO', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function noteFailure(err: unknown, seen: { auth: boolean; config: boolean; first: string | null }) {
  if (err instanceof ApiError) {
    if (err.code === 'NO_BASE_URL') seen.config = true;
    if (err.isAuthError) seen.auth = true;
    if (!seen.first) seen.first = err.message;
  } else if (!seen.first) {
    seen.first = 'Error inesperado al consultar la API.';
  }
}

export interface AlertsDataState {
  isLoading: boolean;
  isAuthBlocked: boolean;
  isConfigMissing: boolean;
  errorMessage: string | null;
  retry: () => void;

  alertsStatus: SectionStatus;
  sessionStatus: SectionStatus;
  notificationsStatus: SectionStatus;

  filter: AlertFilter;
  setFilter: (f: AlertFilter) => void;
  alerts: AlertItem[];
  pendingCount: number;
  criticalCount: number;
  acknowledgedCount: number;

  eventsSummary: EventsSummary | null;
  criticalSessionAlerts: SessionAlert[];
  sessionEvents: SessionEvent[];

  notifications: NotificationRecord[];
  ackingId: string | null;
  ackError: string | null;
  acknowledge: (id: string) => Promise<void>;
}

export function useAlertsData(): AlertsDataState {
  const [attempt, setAttempt] = useState(0);
  const [filter, setFilter] = useState<AlertFilter>('all');
  const [loading, setLoading] = useState(true);
  const [authBlocked, setAuthBlocked] = useState(false);
  const [configMissing, setConfigMissing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [alertsRaw, setAlertsRaw] = useState<AlertItem[]>([]);
  const [alertsFailed, setAlertsFailed] = useState(false);
  const [devices, setDevices] = useState<Device[]>([]);
  const [summary, setSummary] = useState<EventsSummary | null>(null);
  const [criticalSession, setCriticalSession] = useState<SessionAlert[]>([]);
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [sessionFailed, setSessionFailed] = useState(false);
  const [notifications, setNotifications] = useState<NotificationRecord[]>([]);
  const [notificationsFailed, setNotificationsFailed] = useState(false);

  const [ackingId, setAckingId] = useState<string | null>(null);
  const [ackError, setAckError] = useState<string | null>(null);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.allSettled([
      apiGetAlerts({ page: 1, per_page: 50, type: filter === 'all' ? undefined : filter }),
      apiGetDevices({ page: 1, per_page: 100 }),
      apiGetEventsSummary(),
      apiGetCriticalAlerts(10),
      apiGetSessionEvents(20),
      apiGetNotificationHistory({ limit: 50 }),
    ]).then((results) => {
      if (cancelled) return;
      const [alertsRes, devRes, sumRes, critRes, evRes, notRes] = results;
      const seen = { auth: false, config: false, first: null as string | null };

      if (alertsRes.status === 'fulfilled') {
        const devMap = new Map<string, string>();
        if (devRes.status === 'fulfilled') {
          for (const d of devRes.value.results) devMap.set(d.id, d.name);
          setDevices(devRes.value.results);
        } else {
          noteFailure(devRes.reason, seen);
          setDevices([]);
        }
        setAlertsRaw(
          alertsRes.value.results.map((a) => ({
            id: a.id,
            type: a.type,
            label: alertLabel(a.type),
            message: a.message,
            deviceId: a.device_id,
            deviceName: devMap.get(a.device_id) ?? `Dispositivo ${a.device_id.slice(0, 8)}`,
            criticality: a.criticality,
            timestamp: a.created_at,
            acknowledged: a.acknowledged,
          })),
        );
        setAlertsFailed(false);
      } else {
        noteFailure(alertsRes.reason, seen);
        if (devRes.status === 'rejected') noteFailure(devRes.reason, seen);
        setAlertsRaw([]);
        setDevices([]);
        setAlertsFailed(true);
      }

      if (sumRes.status === 'fulfilled' && critRes.status === 'fulfilled' && evRes.status === 'fulfilled') {
        setSummary(sumRes.value);
        setCriticalSession(critRes.value.alerts);
        setEvents(evRes.value.events);
        setSessionFailed(false);
      } else {
        for (const r of [sumRes, critRes, evRes]) {
          if (r.status === 'rejected') noteFailure(r.reason, seen);
        }
        setSummary(null);
        setCriticalSession([]);
        setEvents([]);
        setSessionFailed(true);
      }

      if (notRes.status === 'fulfilled') {
        setNotifications(notRes.value.notifications);
        setNotificationsFailed(false);
      } else {
        noteFailure(notRes.reason, seen);
        setNotifications([]);
        setNotificationsFailed(true);
      }

      setAuthBlocked(seen.auth);
      setConfigMissing(seen.config);
      const allFailed =
        alertsRes.status === 'rejected' &&
        sumRes.status === 'rejected' &&
        critRes.status === 'rejected' &&
        evRes.status === 'rejected' &&
        notRes.status === 'rejected';
      setErrorMessage(allFailed ? seen.first : null);
      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [attempt, filter]);

  const acknowledge = useCallback(async (id: string) => {
    setAckingId(id);
    setAckError(null);
    try {
      await apiAcknowledgeAlert(id);
      // Refetch del historial para reflejar el estado persistido (correctitud > optimismo).
      const [fresh, devRes] = await Promise.all([
        apiGetAlerts({ page: 1, per_page: 50, type: filter === 'all' ? undefined : filter }),
        apiGetDevices({ page: 1, per_page: 100 }).catch(() => null),
      ]);
      const devMap = new Map<string, string>();
      if (devRes) for (const d of devRes.results) devMap.set(d.id, d.name);
      setAlertsRaw(
        fresh.results.map((a) => ({
          id: a.id,
          type: a.type,
          label: alertLabel(a.type),
          message: a.message,
          deviceId: a.device_id,
          deviceName: devMap.get(a.device_id) ?? `Dispositivo ${a.device_id.slice(0, 8)}`,
          criticality: a.criticality,
          timestamp: a.created_at,
          acknowledged: a.acknowledged,
        })),
      );
      setAlertsFailed(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setAckError('La alerta no está disponible en la sesión actual del backend y no pudo reconocerse.');
      } else if (err instanceof ApiError && err.status === 403) {
        setAckError('Sin permiso: el reconocimiento requiere rol administrador, supervisor u operador.');
      } else if (err instanceof Error) {
        setAckError(err.message);
      } else {
        setAckError('No se pudo reconocer la alerta.');
      }
    } finally {
      setAckingId(null);
    }
  }, [filter]);

  const pending = alertsRaw.filter((a) => !a.acknowledged);

  return {
    isLoading: loading,
    isAuthBlocked: authBlocked,
    isConfigMissing: configMissing,
    errorMessage,
    retry,
    alertsStatus: loading ? 'loading' : alertsFailed ? 'error' : alertsRaw.length === 0 ? 'empty' : 'success',
    sessionStatus: loading ? 'loading' : sessionFailed ? 'error' : 'success',
    notificationsStatus: loading ? 'loading' : notificationsFailed ? 'error' : notifications.length === 0 ? 'empty' : 'success',
    filter,
    setFilter,
    alerts: alertsRaw,
    pendingCount: pending.length,
    criticalCount: pending.filter((a) => a.criticality >= 7).length,
    acknowledgedCount: alertsRaw.filter((a) => a.acknowledged).length,
    eventsSummary: summary,
    criticalSessionAlerts: criticalSession,
    sessionEvents: events,
    notifications,
    ackingId,
    ackError,
    acknowledge,
  };
}
