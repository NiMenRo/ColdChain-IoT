// Hook de datos del Dashboard (TSK-048 + polling híbrido).
//
// Patrón: DashboardView → useDashboardData → services/api/* → apiFetch → API.
// - Carga inicial al montar + polling ligero en segundo plano (8 s, pausado
//   con pestaña oculta, sin solapamiento). Sin WebSocket/MQTT.
// - Fuentes /history/* + /devices y resumen de sesión /qos/metrics.
//   La sección QoS usa la misma fuente que la pestaña QoS (useQosSnapshot).
// - Cada sección expone estado loading | success | empty | error para que la
//   vista nunca quede rota ante un fallo de la API.
// - En segundo plano los datos existentes se conservan; solo se informa
//   error discreto y sello de última actualización.

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../../services/api/client';
import { apiGetDevices } from '../../services/api/devices';
import {
  apiGetHistoryAlerts,
  apiGetHistorySummary,
  apiGetReadingTrends,
} from '../../services/api/history';
import type { Device } from '../types/devices';
import { formatMs, formatThroughput } from '../lib/qosUnits';
import { apiGetQosMetrics, type QosMetricsResponse } from '../../services/api/qos';
import { usePolling, DASHBOARD_POLL_MS } from './usePolling';

export type SectionStatus = 'loading' | 'success' | 'empty' | 'error';

export interface DashboardAlertItem {
  id: string;
  type: string;
  label: string;
  deviceName: string;
  criticality: number;
  acknowledged: boolean;
  timestamp: string;
}

export interface QosCell {
  label: string;
  value: string;
  sub: string;
}

export interface EnergySummary {
  on: number;
  off: number;
  /** Proporción de lecturas con energía ON (0–100). Null se representa con objeto null. */
  pctOn: number;
}

export interface TrafficRow {
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
  queue: 'WFQ' | 'Round Robin' | 'FIFO';
  count: number;
  color: string;
  bg: string;
}

// Etiquetas de los 5 tipos válidos de alerta (alineadas con AlertsView).
// Un tipo desconocido se muestra tal cual: nunca se inventa una etiqueta.
const ALERT_TYPE_LABEL: Record<string, string> = {
  TEMPERATURE_EXCEEDED: 'Temperatura Excedida',
  TEMPERATURE_BELOW_MIN: 'Temperatura Bajo Mínimo',
  HUMIDITY_ABOVE_MAX: 'Humedad sobre Máximo',
  HUMIDITY_BELOW_MIN: 'Humedad bajo Mínimo',
  ENERGY_STATE_ANOMALY: 'Anomalía de Estado Energético',
};

function formatClock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}

function statusOf<T>(status: SectionStatus, data: T | null, isEmpty: (d: T) => boolean): SectionStatus {
  if (status === 'error' || status === 'loading') return status;
  if (data === null || isEmpty(data)) return 'empty';
  return 'success';
}

export interface DashboardDataState {
  isLoading: boolean;
  /** Refresco en segundo plano en curso (los datos visibles se conservan). */
  isRefreshing: boolean;
  /** Sello local de la última actualización exitosa (null = ninguna aún). */
  lastUpdated: string | null;
  /** Error solo del último refresco en segundo plano (no borra datos). */
  refreshError: string | null;
  /** Alguna sección falló por falta de autenticación (401: token ausente/inválido). */
  isAuthBlocked: boolean;
  /** Falta VITE_API_BASE_URL. */
  isConfigMissing: boolean;
  errorMessage: string | null;
  retry: () => void;
  /** Actualización manual inmediata (recarga completa). */
  refresh: () => void;

  devicesStatus: SectionStatus;
  alertsStatus: SectionStatus;
  ambientStatus: SectionStatus;
  qosStatus: SectionStatus;
  trafficStatus: SectionStatus;
  energyStatus: SectionStatus;

  totalDevices: number | null;
  activeDevices: number | null;
  errorDevices: number | null;
  totalAlerts: number | null;
  criticalAlerts: number;

  recentAlerts: DashboardAlertItem[];
  avgTemp: number | null;
  avgHumidity: number | null;
  energy: EnergySummary | null;
  qosCells: QosCell[];
  trafficRows: TrafficRow[];
}

export function useDashboardData(): DashboardDataState {
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [authBlocked, setAuthBlocked] = useState(false);
  const [configMissing, setConfigMissing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [devices, setDevices] = useState<Device[] | null>(null);
  const [devicesFailed, setDevicesFailed] = useState(false);
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof apiGetHistorySummary>> | null>(null);
  const [summaryFailed, setSummaryFailed] = useState(false);
  const [alerts, setAlerts] = useState<Awaited<ReturnType<typeof apiGetHistoryAlerts>> | null>(null);
  const [alertsFailed, setAlertsFailed] = useState(false);
  const [readingTrends, setReadingTrends] = useState<Awaited<ReturnType<typeof apiGetReadingTrends>> | null>(null);
  const [readingFailed, setReadingFailed] = useState(false);
  const [qosSession, setQosSession] = useState<QosMetricsResponse | null>(null);
  const [qosFailed, setQosFailed] = useState(false);
  const [pollSeq, setPollSeq] = useState(0);

  const mounted = useRef(true);
  const busyRef = useRef(false);
  const backgroundRef = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

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
      apiGetDevices({ page: 1, per_page: 100 }),
      apiGetHistorySummary(),
      apiGetHistoryAlerts({ page: 1, per_page: 5 }),
      apiGetReadingTrends('hour'),
      apiGetQosMetrics(),
    ]).then((results) => {
      if (cancelled || !mounted.current) return;
      busyRef.current = false;
      const [devRes, sumRes, alertRes, readRes, qosRes] = results;

      let sawAuth = false;
      let sawConfig = false;
      let firstMessage: string | null = null;
      const noteFailure = (r: PromiseRejectedResult) => {
        const reason = r.reason as unknown;
        if (reason instanceof ApiError) {
          if (reason.code === 'NO_BASE_URL') sawConfig = true;
          if (reason.isAuthError) sawAuth = true;
          if (!firstMessage) firstMessage = reason.message;
        } else if (!firstMessage) {
          firstMessage = 'Error inesperado al consultar la API.';
        }
      };

      if (devRes.status === 'fulfilled') {
        setDevices(devRes.value.results);
        setDevicesFailed(false);
      } else {
        noteFailure(devRes);
        // En segundo plano se conservan los últimos datos válidos.
        if (!background) {
          setDevices(null);
          setDevicesFailed(true);
        }
      }
      if (sumRes.status === 'fulfilled') {
        setSummary(sumRes.value);
        setSummaryFailed(false);
      } else {
        noteFailure(sumRes);
        if (!background) {
          setSummary(null);
          setSummaryFailed(true);
        }
      }
      if (alertRes.status === 'fulfilled') {
        setAlerts(alertRes.value);
        setAlertsFailed(false);
      } else {
        noteFailure(alertRes);
        if (!background) {
          setAlerts(null);
          setAlertsFailed(true);
        }
      }
      if (readRes.status === 'fulfilled') {
        setReadingTrends(readRes.value);
        setReadingFailed(false);
      } else {
        noteFailure(readRes);
        if (!background) {
          setReadingTrends(null);
          setReadingFailed(true);
        }
      }
      if (qosRes.status === 'fulfilled') {
        setQosSession(qosRes.value);
        setQosFailed(false);
      } else {
        noteFailure(qosRes);
        if (!background) {
          setQosSession(null);
          setQosFailed(true);
        }
      }

      const fulfilled = [devRes, sumRes, alertRes, readRes, qosRes].filter((r) => r.status === 'fulfilled').length;
      const allFailed = fulfilled === 0;
      if (background) {
        // Error discreto sin borrar nada; el sello solo avanza con datos frescos.
        setRefreshError(allFailed ? (firstMessage ?? 'No se pudo actualizar.') : null);
        if (fulfilled > 0) {
          setLastUpdated(new Date().toLocaleTimeString('es-CO', { hour12: false }));
        }
        setRefreshing(false);
        // 401/403 en segundo plano sí se reflejan (sesión expirada o sin permiso).
        if (sawAuth) setAuthBlocked(true);
        if (sawConfig) setConfigMissing(true);
      } else {
        setAuthBlocked(sawAuth);
        setConfigMissing(sawConfig);
        setErrorMessage(allFailed ? firstMessage : null);
        setLoading(false);
        if (fulfilled > 0) {
          setLastUpdated(new Date().toLocaleTimeString('es-CO', { hour12: false }));
        }
      }
    });

    return () => {
      cancelled = true;
      busyRef.current = false;
    };
  }, [attempt, pollSeq]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  const refresh = useCallback(() => {
    backgroundRef.current = false;
    setAttempt((n) => n + 1);
  }, []);

  // Polling ligero en segundo plano (8 s): refresca sin ocultar datos.
  usePolling(true, DASHBOARD_POLL_MS, useCallback(() => {
    backgroundRef.current = true;
    setPollSeq((n) => n + 1);
  }, []), busyRef);

  // ─── Derivados (solo presentación; ninguna agregación propia del backend) ───

  const deviceById = new Map((devices ?? []).map((d) => [d.id, d]));
  const totalDevices = devices ? devices.length : (summary ? summary.total_devices : null);
  const activeDevices = devices ? devices.filter((d) => d.status === 'active').length : null;
  const errorDevices = devices ? devices.filter((d) => d.status === 'error').length : null;

  const recentAlerts: DashboardAlertItem[] = (alerts?.results ?? []).map((a) => ({
    id: a.id,
    type: a.type,
    label: ALERT_TYPE_LABEL[a.type] ?? a.type,
    deviceName: deviceById.get(a.device_id)?.name ?? `Dispositivo ${a.device_id.slice(0, 8)}`,
    criticality: a.criticality,
    acknowledged: a.acknowledged,
    timestamp: formatClock(a.created_at),
  }));
  const totalAlerts = summary ? summary.total_alerts : (alerts ? alerts.total : null);
  const criticalAlerts = recentAlerts.filter((a) => a.criticality >= 7 && !a.acknowledged).length;

  const lastReading = [...(readingTrends ?? [])].reverse().find((p) => p.avg_temp !== null || p.avg_hum !== null);
  const avgTemp = lastReading?.avg_temp ?? null;
  const avgHumidity = lastReading?.avg_hum ?? null;

  // Misma fuente y formato que la pestaña QoS (useQosSnapshot):
  // resumen de sesión /qos/metrics. Sin datos de sesión → sin celdas.
  const qosCells: QosCell[] = qosSession && qosSession.count > 0
    ? [
        { label: 'Latencia media', value: formatMs(qosSession.summary.latency), sub: 'Sesión actual' },
        { label: 'Jitter', value: formatMs(qosSession.summary.jitter), sub: 'Sesión actual' },
        { label: 'Pérdida paquetes', value: `${qosSession.summary.packet_loss.toFixed(1)} %`, sub: 'Sesión actual' },
        { label: 'PDR', value: `${qosSession.summary.pdr.toFixed(1)} %`, sub: 'Tasa de entrega' },
        { label: 'Throughput', value: formatThroughput(qosSession.summary.throughput), sub: 'Promedio sesión' },
      ]
    : [];

  // Proporción de lecturas con energía ON (agregado del backend, sin
  // agregación propia). Null cuando no hay lecturas con estado registrado.
  const energyByState = summary?.energy_by_state ?? {};
  const energyOn = typeof energyByState.on === 'number' ? energyByState.on : 0;
  const energyOff = typeof energyByState.off === 'number' ? energyByState.off : 0;
  const energyTotal = energyOn + energyOff;
  const energy: EnergySummary | null = summary && !summaryFailed && energyTotal > 0
    ? { on: energyOn, off: energyOff, pctOn: (energyOn / energyTotal) * 100 }
    : null;

  const traffic = summary?.traffic_by_priority ?? {};
  const trafficCounts = {
    HIGH: typeof traffic.high === 'number' ? traffic.high : 0,
    MEDIUM: typeof traffic.medium === 'number' ? traffic.medium : 0,
    LOW: typeof traffic.low === 'number' ? traffic.low : 0,
  };
  const trafficRows: TrafficRow[] = [
    { priority: 'HIGH', queue: 'WFQ', count: trafficCounts.HIGH, color: '#C83B3B', bg: '#FCEEEE' },
    { priority: 'MEDIUM', queue: 'Round Robin', count: trafficCounts.MEDIUM, color: '#C47A00', bg: '#FFF5E3' },
    { priority: 'LOW', queue: 'FIFO', count: trafficCounts.LOW, color: '#16835B', bg: '#EAF6EF' },
  ];

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
    devicesStatus: loading ? 'loading' : devicesFailed ? 'error' : statusOf('success', devices, (d) => d.length === 0),
    alertsStatus: loading ? 'loading' : alertsFailed ? 'error' : statusOf('success', recentAlerts, (d) => d.length === 0),
    ambientStatus: loading ? 'loading' : readingFailed ? 'error' : statusOf('success', lastReading ?? null, () => false),
    qosStatus: loading ? 'loading' : qosFailed ? 'error' : statusOf('success', qosCells, (d) => d.length === 0),
    trafficStatus: loading ? 'loading' : summaryFailed ? 'error' : statusOf('success', trafficRows, (d) => d.every((r) => r.count === 0)),
    energyStatus: loading ? 'loading' : summaryFailed ? 'error' : statusOf('success', energy, (d) => d === null),
    totalDevices,
    activeDevices,
    errorDevices,
    totalAlerts,
    criticalAlerts,
    recentAlerts,
    avgTemp,
    avgHumidity,
    energy,
    qosCells,
    trafficRows,
  };
}
