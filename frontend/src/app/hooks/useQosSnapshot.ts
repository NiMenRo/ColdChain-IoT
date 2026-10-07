// Hook de snapshot QoS disponible (TSK-050).
//
// Fuentes reales: GET /qos/metrics (resumen de sesión) y las filas más
// recientes de GET /history/qos (persistido). Solo disponibilidad actual;
// el análisis histórico y la comparación con/sin priorización pertenecen
// a TSK-052 y quedan fuera.

import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../../services/api/client';
import { apiGetQosMetrics } from '../../services/api/qos';
import { apiGetQosRecords, type QosRecord } from '../../services/api/history';

export type SectionStatus = 'loading' | 'success' | 'empty' | 'error';

export interface QosCell {
  label: string;
  value: string;
  sub: string;
}

export interface QosSnapshotState {
  isLoading: boolean;
  isAuthBlocked: boolean;
  isConfigMissing: boolean;
  errorMessage: string | null;
  retry: () => void;
  status: SectionStatus;
  cells: QosCell[];
  recordCount: number;
  recent: QosRecord[];
  recentStatus: SectionStatus;
}

export function useQosSnapshot(): QosSnapshotState {
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [authBlocked, setAuthBlocked] = useState(false);
  const [configMissing, setConfigMissing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [summary, setSummary] = useState<{ latency: number; jitter: number; throughput: number; pdr: number; packet_loss: number } | null>(null);
  const [count, setCount] = useState(0);
  const [summaryFailed, setSummaryFailed] = useState(false);
  const [recent, setRecent] = useState<QosRecord[]>([]);
  const [recentFailed, setRecentFailed] = useState(false);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.allSettled([apiGetQosMetrics(), apiGetQosRecords({ per_page: 5 })]).then(([mRes, rRes]) => {
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

      if (mRes.status === 'fulfilled') {
        setSummary(mRes.value.summary);
        setCount(mRes.value.count);
        setSummaryFailed(false);
      } else {
        note(mRes.reason);
        setSummary(null);
        setCount(0);
        setSummaryFailed(true);
      }

      if (rRes.status === 'fulfilled') {
        setRecent(rRes.value.results);
        setRecentFailed(false);
      } else {
        note(rRes.reason);
        setRecent([]);
        setRecentFailed(true);
      }

      setAuthBlocked(auth);
      setConfigMissing(config);
      setErrorMessage(mRes.status === 'rejected' && rRes.status === 'rejected' ? first : null);
      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const hasData = summary !== null && count > 0;
  const cells: QosCell[] = summary && count > 0
    ? [
        { label: 'Latencia media', value: `${summary.latency.toFixed(0)} ms`, sub: 'Sesión actual' },
        { label: 'Jitter', value: `${summary.jitter.toFixed(1)} ms`, sub: 'Sesión actual' },
        { label: 'Pérdida de paquetes', value: `${summary.packet_loss.toFixed(1)} %`, sub: 'Sesión actual' },
        { label: 'PDR', value: `${summary.pdr.toFixed(1)} %`, sub: 'Tasa de entrega' },
        { label: 'Throughput', value: `${summary.throughput.toFixed(1)}`, sub: 'Promedio sesión' },
      ]
    : [];

  return {
    isLoading: loading,
    isAuthBlocked: authBlocked,
    isConfigMissing: configMissing,
    errorMessage,
    retry,
    status: loading ? 'loading' : summaryFailed ? 'error' : !hasData ? 'empty' : 'success',
    cells,
    recordCount: count,
    recent,
    recentStatus: loading ? 'loading' : recentFailed ? 'error' : recent.length === 0 ? 'empty' : 'success',
  };
}
