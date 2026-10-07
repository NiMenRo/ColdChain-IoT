// Hook de datos del Dashboard (TSK-048).
//
// Patrón: DashboardView → useDashboardData → services/api/* → apiFetch → API.
// - Una sola carga al montar (+ reintento manual). Sin polling, sin WebSocket/MQTT.
// - Fuentes exclusivamente persistidas /history/* + /devices (nunca runtime).
// - Cada sección expone estado loading | success | empty | error para que la
//   vista nunca quede rota ante un fallo de la API.

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../../services/api/client';
import { apiGetDevices } from '../../services/api/devices';
import {
  apiGetHistoryAlerts,
  apiGetHistorySummary,
  apiGetQosTrends,
  apiGetReadingTrends,
} from '../../services/api/history';
import type { Device } from '../types/devices';

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
  /** Alguna sección falló por falta de autenticación (auth mock pendiente). */
  isAuthBlocked: boolean;
  /** Falta VITE_API_BASE_URL. */
  isConfigMissing: boolean;
  errorMessage: string | null;
  retry: () => void;

  devicesStatus: SectionStatus;
  alertsStatus: SectionStatus;
  ambientStatus: SectionStatus;
  qosStatus: SectionStatus;
  trafficStatus: SectionStatus;

  totalDevices: number | null;
  activeDevices: number | null;
  errorDevices: number | null;
  totalAlerts: number | null;
  criticalAlerts: number;

  recentAlerts: DashboardAlertItem[];
  avgTemp: number | null;
  avgHumidity: number | null;
  qosCells: QosCell[];
  trafficRows: TrafficRow[];
}

export function useDashboardData(): DashboardDataState {
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
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
  const [qosTrends, setQosTrends] = useState<Awaited<ReturnType<typeof apiGetQosTrends>> | null>(null);
  const [qosFailed, setQosFailed] = useState(false);

  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.allSettled([
      apiGetDevices({ page: 1, per_page: 100 }),
      apiGetHistorySummary(),
      apiGetHistoryAlerts({ page: 1, per_page: 5 }),
      apiGetReadingTrends('hour'),
      apiGetQosTrends('hour'),
    ]).then((results) => {
      if (cancelled || !mounted.current) return;
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
        setDevices(null);
        setDevicesFailed(true);
      }
      if (sumRes.status === 'fulfilled') {
        setSummary(sumRes.value);
        setSummaryFailed(false);
      } else {
        noteFailure(sumRes);
        setSummary(null);
        setSummaryFailed(true);
      }
      if (alertRes.status === 'fulfilled') {
        setAlerts(alertRes.value);
        setAlertsFailed(false);
      } else {
        noteFailure(alertRes);
        setAlerts(null);
        setAlertsFailed(true);
      }
      if (readRes.status === 'fulfilled') {
        setReadingTrends(readRes.value);
        setReadingFailed(false);
      } else {
        noteFailure(readRes);
        setReadingTrends(null);
        setReadingFailed(true);
      }
      if (qosRes.status === 'fulfilled') {
        setQosTrends(qosRes.value);
        setQosFailed(false);
      } else {
        noteFailure(qosRes);
        setQosTrends(null);
        setQosFailed(true);
      }

      setAuthBlocked(sawAuth);
      setConfigMissing(sawConfig);
      const allFailed = [devRes, sumRes, alertRes, readRes, qosRes].every((r) => r.status === 'rejected');
      setErrorMessage(allFailed ? firstMessage : null);
      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

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

  const lastQos = qosTrends && qosTrends.length > 0 ? qosTrends[qosTrends.length - 1] : null;
  const qosCells: QosCell[] = lastQos
    ? [
        { label: 'Latencia', value: `${lastQos.avg_latency.toFixed(0)} ms` },
        { label: 'Jitter', value: `${lastQos.avg_jitter.toFixed(1)} ms` },
        { label: 'Pérdida paquetes', value: `${lastQos.avg_packet_loss.toFixed(1)} %` },
        { label: 'PDR', value: `${lastQos.avg_pdr.toFixed(1)} %` },
      ]
    : [];

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
    isAuthBlocked: authBlocked,
    isConfigMissing: configMissing,
    errorMessage,
    retry,
    devicesStatus: loading ? 'loading' : devicesFailed ? 'error' : statusOf('success', devices, (d) => d.length === 0),
    alertsStatus: loading ? 'loading' : alertsFailed ? 'error' : statusOf('success', recentAlerts, (d) => d.length === 0),
    ambientStatus: loading ? 'loading' : readingFailed ? 'error' : statusOf('success', lastReading ?? null, () => false),
    qosStatus: loading ? 'loading' : qosFailed ? 'error' : statusOf('success', qosCells, (d) => d.length === 0),
    trafficStatus: loading ? 'loading' : summaryFailed ? 'error' : statusOf('success', trafficRows, (d) => d.every((r) => r.count === 0)),
    totalDevices,
    activeDevices,
    errorDevices,
    totalAlerts,
    criticalAlerts,
    recentAlerts,
    avgTemp,
    avgHumidity,
    qosCells,
    trafficRows,
  };
}
