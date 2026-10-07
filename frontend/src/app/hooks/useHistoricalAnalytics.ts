// Hook de análisis histórico (TSK-052).
//
// Patrón: View → useHistoricalAnalytics → services/api/history → apiFetch.
// - Periodo 24h|7d|30d → from_ts/to_ts + interval hour|hour|day. El filtrado
//   temporal lo ejecuta el backend; el frontend nunca simula filtrado.
// - Agregados (priority/queue/alert-type) directo de GET /history/summary.
// - ÚNICAS transformaciones frontend autorizadas, sobre muestras paginadas
//   acotadas (≤100) y etiquetadas como muestra, nunca como global:
//   bucketing de criticidad por rangos y conteo de alertas por día.
// Una sola carga al montar (+ cambio de periodo + retry). Sin polling.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError } from '../../services/api/client';
import {
  apiGetClassifications,
  apiGetHistoryAlerts,
  apiGetHistorySummary,
  apiGetQosTrends,
  apiGetReadingTrends,
  type HistoryClassification,
  type HistoryInterval,
  type HistorySummary,
  type QosTrendPoint,
  type ReadingTrendPoint,
} from '../../services/api/history';

export type SectionStatus = 'loading' | 'success' | 'empty' | 'error';
export type HistoryRange = '24h' | '7d' | '30d';

/** Muestra máxima para las agrupaciones de presentación autorizadas. */
export const SAMPLE_LIMIT = 100;

export interface RangeOption {
  value: HistoryRange;
  label: string;
  interval: HistoryInterval;
  days: number;
}

export const RANGE_OPTIONS: RangeOption[] = [
  { value: '24h', label: 'Últimas 24 h', interval: 'hour', days: 1 },
  { value: '7d', label: 'Últimos 7 días', interval: 'hour', days: 7 },
  { value: '30d', label: 'Últimos 30 días', interval: 'day', days: 30 },
];

export interface CriticalityBucket {
  range: string;
  count: number;
  color: string;
}

const CRITICALITY_BUCKETS: Array<{ range: string; min: number; max: number; color: string }> = [
  { range: '3.0 – 4.9', min: 3.0, max: 4.9, color: '#16835B' },
  { range: '5.0 – 6.9', min: 5.0, max: 6.9, color: '#C47A00' },
  { range: '7.0 – 9.0', min: 7.0, max: 9.0, color: '#C83B3B' },
];

export interface AlertsPerDay {
  day: string;
  count: number;
}

function toIso(d: Date): string {
  return d.toISOString();
}

export interface HistoricalAnalyticsState {
  range: HistoryRange;
  setRange: (r: HistoryRange) => void;
  rangeLabel: string;
  isLoading: boolean;
  isAuthBlocked: boolean;
  isConfigMissing: boolean;
  errorMessage: string | null;
  retry: () => void;

  readingStatus: SectionStatus;
  readingTrends: ReadingTrendPoint[];
  qosStatus: SectionStatus;
  qosTrends: QosTrendPoint[];
  summaryStatus: SectionStatus;
  summary: HistorySummary | null;
  classStatus: SectionStatus;
  criticalityBuckets: CriticalityBucket[];
  classSampleCount: number;
  /** Muestra acotada (timestamp + criticidad) para evolución temporal. */
  classSample: Array<{ timestamp: string; criticality: number }>;
  alertsStatus: SectionStatus;
  alertsPerDay: AlertsPerDay[];
  alertsSampleCount: number;
}

export function useHistoricalAnalytics(): HistoricalAnalyticsState {
  const [range, setRange] = useState<HistoryRange>('7d');
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [authBlocked, setAuthBlocked] = useState(false);
  const [configMissing, setConfigMissing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [readingTrends, setReadingTrends] = useState<ReadingTrendPoint[]>([]);
  const [readingFailed, setReadingFailed] = useState(false);
  const [qosTrends, setQosTrends] = useState<QosTrendPoint[]>([]);
  const [qosFailed, setQosFailed] = useState(false);
  const [summary, setSummary] = useState<HistorySummary | null>(null);
  const [summaryFailed, setSummaryFailed] = useState(false);
  const [classifications, setClassifications] = useState<HistoryClassification[]>([]);
  const [classFailed, setClassFailed] = useState(false);
  const [alertsRaw, setAlertsRaw] = useState<Array<{ created_at: string }>>([]);
  const [alertsFailed, setAlertsFailed] = useState(false);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  const option = RANGE_OPTIONS.find((o) => o.value === range) ?? RANGE_OPTIONS[1];
  const to = useMemo(() => new Date(), [range, attempt]);
  const from = useMemo(() => new Date(to.getTime() - option.days * 24 * 60 * 60 * 1000), [to, option.days]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const fromTs = toIso(from);
    const toTs = toIso(to);

    Promise.allSettled([
      apiGetReadingTrends(option.interval, { from_ts: fromTs, to_ts: toTs }),
      apiGetQosTrends(option.interval, { from_ts: fromTs, to_ts: toTs }),
      apiGetHistorySummary(),
      apiGetClassifications({ page: 1, per_page: SAMPLE_LIMIT, sort: 'timestamp.desc', from_ts: fromTs, to_ts: toTs }),
      apiGetHistoryAlerts({ page: 1, per_page: SAMPLE_LIMIT, sort: 'created_at.desc', from_ts: fromTs, to_ts: toTs }),
    ]).then(([readRes, qosRes, sumRes, clsRes, alertRes]) => {
      if (cancelled) return;
      let auth = false;
      let config = false;
      let first: string | null = null;
      const note = (reason: unknown) => {
        if (reason instanceof ApiError) {
          if (reason.code === 'NO_BASE_URL') config = true;
          if (reason.isAuthError) auth = true;
          if (!first) first = reason.message;
        } else if (!first) {
          first = 'Error inesperado al consultar la API.';
        }
      };

      if (readRes.status === 'fulfilled') {
        setReadingTrends(readRes.value);
        setReadingFailed(false);
      } else {
        note(readRes.reason);
        setReadingTrends([]);
        setReadingFailed(true);
      }
      if (qosRes.status === 'fulfilled') {
        setQosTrends(qosRes.value);
        setQosFailed(false);
      } else {
        note(qosRes.reason);
        setQosTrends([]);
        setQosFailed(true);
      }
      if (sumRes.status === 'fulfilled') {
        setSummary(sumRes.value);
        setSummaryFailed(false);
      } else {
        note(sumRes.reason);
        setSummary(null);
        setSummaryFailed(true);
      }
      if (clsRes.status === 'fulfilled') {
        setClassifications(clsRes.value.results);
        setClassFailed(false);
      } else {
        note(clsRes.reason);
        setClassifications([]);
        setClassFailed(true);
      }
      if (alertRes.status === 'fulfilled') {
        setAlertsRaw(alertRes.value.results.map((a) => ({ created_at: a.created_at })));
        setAlertsFailed(false);
      } else {
        note(alertRes.reason);
        setAlertsRaw([]);
        setAlertsFailed(true);
      }

      setAuthBlocked(auth);
      setConfigMissing(config);
      const allFailed = [readRes, qosRes, sumRes, clsRes, alertRes].every((r) => r.status === 'rejected');
      setErrorMessage(allFailed ? first : null);
      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range, attempt]);

  // Agrupación de presentación autorizada: muestra acotada, nunca global.
  const criticalityBuckets: CriticalityBucket[] = useMemo(
    () =>
      CRITICALITY_BUCKETS.map((b) => ({
        range: b.range,
        color: b.color,
        count: classifications.filter((c) => c.criticality >= b.min && c.criticality <= b.max).length,
      })),
    [classifications],
  );

  const alertsPerDay: AlertsPerDay[] = useMemo(() => {
    const byDay = new Map<string, number>();
    for (const a of alertsRaw) {
      const d = new Date(a.created_at);
      if (Number.isNaN(d.getTime())) continue;
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      byDay.set(key, (byDay.get(key) ?? 0) + 1);
    }
    return [...byDay.entries()]
      .sort(([a], [b]) => (a < b ? -1 : 1))
      .map(([day, count]) => ({ day: day.slice(5), count }));
  }, [alertsRaw]);

  return {
    range,
    setRange,
    rangeLabel: option.label,
    isLoading: loading,
    isAuthBlocked: authBlocked,
    isConfigMissing: configMissing,
    errorMessage,
    retry,
    readingStatus: loading ? 'loading' : readingFailed ? 'error' : readingTrends.length === 0 ? 'empty' : 'success',
    readingTrends,
    qosStatus: loading ? 'loading' : qosFailed ? 'error' : qosTrends.length === 0 ? 'empty' : 'success',
    qosTrends,
    summaryStatus: loading ? 'loading' : summaryFailed ? 'error' : !summary ? 'empty' : 'success',
    summary,
    classStatus: loading ? 'loading' : classFailed ? 'error' : classifications.length === 0 ? 'empty' : 'success',
    criticalityBuckets,
    classSampleCount: classifications.length,
    classSample: classifications.map((c) => ({ timestamp: c.timestamp, criticality: c.criticality })),
    alertsStatus: loading ? 'loading' : alertsFailed ? 'error' : alertsRaw.length === 0 ? 'empty' : 'success',
    alertsPerDay,
    alertsSampleCount: alertsRaw.length,
  };
}
