// Hook de alertas, eventos de sesión y notificaciones (TSK-050 + polling híbrido + fase C).
//
// Patrón: AlertsView → useAlertsData → services/api/* → apiFetch → Backend.
// - Historial persistido: GET /history/alerts (filtro `type` server-side).
// - Sesión runtime: GET /events/summary, /events/alerts/critical, /events/events.
// - Notificaciones: GET /notifications/persistent (historial durable propio,
//   con is_read). El endpoint runtime /notifications/history queda sin uso en
//   la UI (prototipo conservado en el backend).
// - Reconocimiento: POST /notifications/alerts/{id}/acknowledge + refetch.
//   No toca is_read (independencia lectura ↔ reconocimiento).
// - Lectura: PATCH /notifications/{id}/read + POST /notifications/read-all
//   (parche local inmediato + evento para la campana, sin refetch pesado).
// Carga inicial al montar + polling ligero en segundo plano (10 s, página 1 =
// registros recientes, sin duplicados por `id`). Sin realtime push.

import { useCallback, useEffect, useRef, useState } from 'react';
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
  apiGetPersistentHistory,
  apiMarkAllNotificationsRead,
  apiMarkNotificationRead,
  notifyNotificationsChanged,
  type NotificationRecord,
} from '../../services/api/notifications';
import { usePolling, ALERTS_POLL_MS } from './usePolling';
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
  /** Refresco en segundo plano en curso (los datos visibles se conservan). */
  isRefreshing: boolean;
  /** Sello local de la última actualización exitosa (null = ninguna aún). */
  lastUpdated: string | null;
  /** Error solo del último refresco en segundo plano (no borra datos). */
  refreshError: string | null;
  isAuthBlocked: boolean;
  isConfigMissing: boolean;
  errorMessage: string | null;
  retry: () => void;
  /** Actualización manual inmediata (recarga completa). */
  refresh: () => void;

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
  /** No leídas dentro de la página cargada (el total exacto vive en la
   * campana vía /unread-count; este hook no duplica esa consulta). */
  unreadCount: number;
  ackingId: string | null;
  ackError: string | null;
  acknowledge: (id: string) => Promise<void>;
  readingId: string | null;
  readError: string | null;
  markRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
}

export function useAlertsData(): AlertsDataState {
  const [attempt, setAttempt] = useState(0);
  const [pollSeq, setPollSeq] = useState(0);
  const [filter, setFilter] = useState<AlertFilter>('all');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const busyRef = useRef(false);
  const backgroundRef = useRef(false);
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);
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
  const [readingId, setReadingId] = useState<string | null>(null);
  const [readError, setReadError] = useState<string | null>(null);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  const refresh = useCallback(() => {
    backgroundRef.current = false;
    setAttempt((n) => n + 1);
  }, []);

  // Polling ligero (10 s) sobre la página 1 = registros recientes.
  // Sin duplicados: la lista se reemplaza por `id` desde el backend.
  usePolling(true, ALERTS_POLL_MS, useCallback(() => {
    backgroundRef.current = true;
    setPollSeq((n) => n + 1);
  }, []), busyRef);

  useEffect(() => {
    let cancelled = false;
    const background = backgroundRef.current;
    backgroundRef.current = false;
    if (background) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    busyRef.current = true;

    Promise.allSettled([
      apiGetAlerts({ page: 1, per_page: 50, type: filter === 'all' ? undefined : filter }),
      apiGetDevices({ page: 1, per_page: 100 }),
      apiGetEventsSummary(),
      apiGetCriticalAlerts(10),
      apiGetSessionEvents(20),
      apiGetPersistentHistory({ limit: 50 }),
    ]).then((results) => {
      if (cancelled || !mountedRef.current) return;
      busyRef.current = false;
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
        // En segundo plano se conservan los últimos datos válidos.
        if (!background) {
          setAlertsRaw([]);
          setDevices([]);
          setAlertsFailed(true);
        }
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
        if (!background) {
          setSummary(null);
          setCriticalSession([]);
          setEvents([]);
          setSessionFailed(true);
        }
      }

      if (notRes.status === 'fulfilled') {
        setNotifications(notRes.value.notifications);
        setNotificationsFailed(false);
      } else {
        noteFailure(notRes.reason, seen);
        if (!background) {
          setNotifications([]);
          setNotificationsFailed(true);
        }
      }

      const anyOk =
        alertsRes.status === 'fulfilled' ||
        sumRes.status === 'fulfilled' ||
        notRes.status === 'fulfilled';
      if (background) {
        setRefreshError(anyOk ? null : (seen.first ?? 'No se pudo actualizar.'));
        if (anyOk) {
          setLastUpdated(new Date().toLocaleTimeString('es-CO', { hour12: false }));
        }
        setRefreshing(false);
        if (seen.auth) setAuthBlocked(true);
        if (seen.config) setConfigMissing(true);
      } else {
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
      }
    });

    return () => {
      cancelled = true;
      busyRef.current = false;
    };
  }, [attempt, filter, pollSeq]);

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

  // Lectura de notificaciones (fase C): parche local inmediato + evento
  // para la campana. No refetch: el polling de 10 s reconcilia. No toca
  // `acknowledged` de ninguna alerta (independencia total).
  const markRead = useCallback(async (id: string) => {
    setReadingId(id);
    setReadError(null);
    try {
      const res = await apiMarkNotificationRead(id);
      const updated = res.notification;
      setNotifications((prev) =>
        prev.map((n) => (n.id === id
          ? { ...n, is_read: true, read_at: updated.read_at ?? n.read_at }
          : n)),
      );
      setNotificationsFailed(false);
      notifyNotificationsChanged();
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setReadError('La notificación no existe o pertenece a otro usuario.');
      } else if (err instanceof Error) {
        setReadError(err.message);
      } else {
        setReadError('No se pudo marcar la notificación como leída.');
      }
    } finally {
      setReadingId(null);
    }
  }, []);

  const markAllRead = useCallback(async () => {
    setReadingId('__all__');
    setReadError(null);
    try {
      const res = await apiMarkAllNotificationsRead();
      if (res.updated > 0) {
        setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
        notifyNotificationsChanged();
      }
    } catch (err) {
      if (err instanceof Error) {
        setReadError(err.message);
      } else {
        setReadError('No se pudieron marcar las notificaciones como leídas.');
      }
    } finally {
      setReadingId(null);
    }
  }, []);

  const pending = alertsRaw.filter((a) => !a.acknowledged);

  return {
    isLoading: loading,
    isRefreshing: refreshing,
    lastUpdated,
    refreshError,
    isAuthBlocked: authBlocked,
    isConfigMissing: configMissing,
    errorMessage,
    retry,
    refresh,
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
    unreadCount: notifications.filter((n) => !n.is_read).length,
    ackingId,
    ackError,
    acknowledge,
    readingId,
    readError,
    markRead,
    markAllRead,
  };
}
