// Hook de clasificación de tráfico (TSK-050).
//
// Fuentes reales: GET /history/summary (conteos agregados por el backend) y
// GET /history/classifications (filas recientes con criticality/priority/queue).
// No se construye ninguna serie temporal en frontend (sin endpoint que la respalde).

import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../../services/api/client';
import {
  apiGetClassifications,
  apiGetHistorySummary,
  type HistoryClassification,
} from '../../services/api/history';

export type SectionStatus = 'loading' | 'success' | 'empty' | 'error';

export interface TrafficRow {
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
  queue: 'WFQ' | 'Round Robin' | 'FIFO';
  description: string;
  count: number;
  pct: number;
  color: string;
  bg: string;
  border: string;
}

const ROW_META: Array<Omit<TrafficRow, 'count' | 'pct'>> = [
  {
    priority: 'HIGH', queue: 'WFQ', color: '#C83B3B', bg: '#FCEEEE', border: '#f1aeb5',
    description: 'Alertas críticas y lecturas fuera de rango. Procesamiento prioritario garantizado.',
  },
  {
    priority: 'MEDIUM', queue: 'Round Robin', color: '#C47A00', bg: '#FFF5E3', border: '#ffda6a',
    description: 'Telemetría periódica estándar. Distribución equitativa entre dispositivos.',
  },
  {
    priority: 'LOW', queue: 'FIFO', color: '#16835B', bg: '#EAF6EF', border: '#a3cfbb',
    description: 'Datos de diagnóstico, logs y lecturas de baja frecuencia.',
  },
];

export interface TrafficDataState {
  isLoading: boolean;
  isAuthBlocked: boolean;
  isConfigMissing: boolean;
  errorMessage: string | null;
  retry: () => void;
  status: SectionStatus;
  rows: TrafficRow[];
  total: number;
  recent: HistoryClassification[];
  recentStatus: SectionStatus;
}

export function useTrafficData(): TrafficDataState {
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [authBlocked, setAuthBlocked] = useState(false);
  const [configMissing, setConfigMissing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [counts, setCounts] = useState<{ high: number; medium: number; low: number } | null>(null);
  const [countsFailed, setCountsFailed] = useState(false);
  const [recent, setRecent] = useState<HistoryClassification[]>([]);
  const [recentFailed, setRecentFailed] = useState(false);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.allSettled([
      apiGetHistorySummary(),
      apiGetClassifications({ page: 1, per_page: 10 }),
    ]).then(([sumRes, clsRes]) => {
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

      if (sumRes.status === 'fulfilled') {
        const t = sumRes.value.traffic_by_priority ?? {};
        setCounts({
          high: typeof t.high === 'number' ? t.high : 0,
          medium: typeof t.medium === 'number' ? t.medium : 0,
          low: typeof t.low === 'number' ? t.low : 0,
        });
        setCountsFailed(false);
      } else {
        note(sumRes.reason);
        setCounts(null);
        setCountsFailed(true);
      }

      if (clsRes.status === 'fulfilled') {
        setRecent(clsRes.value.results);
        setRecentFailed(false);
      } else {
        note(clsRes.reason);
        setRecent([]);
        setRecentFailed(true);
      }

      setAuthBlocked(auth);
      setConfigMissing(config);
      setErrorMessage(sumRes.status === 'rejected' && clsRes.status === 'rejected' ? first : null);
      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const total = counts ? counts.high + counts.medium + counts.low : 0;
  const rows: TrafficRow[] = ROW_META.map((meta) => {
    const count = counts
      ? meta.priority === 'HIGH' ? counts.high : meta.priority === 'MEDIUM' ? counts.medium : counts.low
      : 0;
    return { ...meta, count, pct: total > 0 ? (count / total) * 100 : 0 };
  });

  return {
    isLoading: loading,
    isAuthBlocked: authBlocked,
    isConfigMissing: configMissing,
    errorMessage,
    retry,
    status: loading ? 'loading' : countsFailed ? 'error' : total === 0 ? 'empty' : 'success',
    rows,
    total,
    recent,
    recentStatus: loading ? 'loading' : recentFailed ? 'error' : recent.length === 0 ? 'empty' : 'success',
  };
}
