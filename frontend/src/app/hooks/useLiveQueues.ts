// Colas QoS en vivo (FIFO / Round Robin / WFQ).
//
// Fuente única: GET /qos/queues — snapshot del contenido actual de los
// schedulers en memoria del backend. Es GLOBAL (todas las ejecuciones y
// tráfico manual), INSTANTÁNEO (cambia con cada mensaje) y VOLÁTIL (se
// vacía al reiniciar el backend). No admite filtro run_id: presentarlo
// como dato de una ejecución sería falso.
// Polling ligero reutilizando usePolling (pausa con pestaña oculta).

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../../services/api/client';
import { apiGetLiveQueues, type LiveQueueItem } from '../../services/api/qos';
import { ALERTS_POLL_MS, usePolling } from './usePolling';

export type SectionStatus = 'loading' | 'success' | 'empty' | 'error';

export interface LiveQueueSnapshot {
  priority: 'low' | 'medium' | 'high';
  queue: 'FIFO' | 'Round Robin' | 'WFQ';
  count: number;
  sample: LiveQueueItem[];
}

const META: Array<{ priority: LiveQueueSnapshot['priority']; queue: LiveQueueSnapshot['queue'] }> = [
  { priority: 'high', queue: 'WFQ' },
  { priority: 'medium', queue: 'Round Robin' },
  { priority: 'low', queue: 'FIFO' },
];

export interface LiveQueuesState {
  isLoading: boolean;
  isAuthBlocked: boolean;
  isConfigMissing: boolean;
  errorMessage: string | null;
  retry: () => void;
  status: SectionStatus;
  total: number;
  queues: LiveQueueSnapshot[];
}

export function useLiveQueues(): LiveQueuesState {
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [authBlocked, setAuthBlocked] = useState(false);
  const [configMissing, setConfigMissing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [queues, setQueues] = useState<LiveQueueSnapshot[]>([]);
  const [failed, setFailed] = useState(false);
  const busyRef = useRef(false);
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  usePolling(true, ALERTS_POLL_MS, useCallback(() => {
    setAttempt((n) => n + 1);
  }, []), busyRef);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    busyRef.current = true;
    apiGetLiveQueues().then(
      (res) => {
        if (cancelled || !mountedRef.current) return;
        busyRef.current = false;
        setQueues(
          META.map((m) => {
            const items = res.queues?.[m.priority] ?? [];
            return {
              ...m,
              count: items.length,
              sample: items.slice(0, 5),
            };
          }),
        );
        setFailed(false);
        setAuthBlocked(false);
        setConfigMissing(false);
        setErrorMessage(null);
        setLoading(false);
      },
      (err: unknown) => {
        if (cancelled || !mountedRef.current) return;
        busyRef.current = false;
        const apiErr = err instanceof ApiError ? err : null;
        setQueues([]);
        setFailed(true);
        setAuthBlocked(apiErr !== null && apiErr.isAuthError);
        setConfigMissing(apiErr?.code === 'NO_BASE_URL');
        setErrorMessage(err instanceof Error ? err.message : 'No se pudieron cargar las colas.');
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
      busyRef.current = false;
    };
  }, [attempt]);

  const total = queues.reduce((s, q) => s + q.count, 0);
  return {
    isLoading: loading,
    isAuthBlocked: authBlocked,
    isConfigMissing: configMissing,
    errorMessage,
    retry,
    status: loading ? 'loading' : failed ? 'error' : total === 0 ? 'empty' : 'success',
    total,
    queues,
  };
}
