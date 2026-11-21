// Runtime productivo del despacho QoS (GET /qos/runtime).
//
// Fuente única: el coordinador que realmente admite y atiende lecturas. Es
// distinto de GET /qos/queues, que sigue ilustrando el planner de demostración.
// El backend responde 409 cuando el pipeline no está activo: eso es un estado
// «detenido» esperado, no un error de red. Polling ligero con usePolling
// (pausa con pestaña oculta) y sin inventar valores: los campos nullable se
// conservan como null para que la vista muestre «—».

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../../services/api/client';
import { apiGetQosRuntime, type QosRuntimeResponse } from '../../services/api/qos';
import { ALERTS_POLL_MS, usePolling } from './usePolling';

export type QosRuntimeStatus = 'loading' | 'running' | 'stopped' | 'error';

export interface QosRuntimeState {
  isLoading: boolean;
  isAuthBlocked: boolean;
  isConfigMissing: boolean;
  errorMessage: string | null;
  retry: () => void;
  status: QosRuntimeStatus;
  runtime: QosRuntimeResponse | null;
}

export function useQosRuntime(): QosRuntimeState {
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [authBlocked, setAuthBlocked] = useState(false);
  const [configMissing, setConfigMissing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [runtime, setRuntime] = useState<QosRuntimeResponse | null>(null);
  const [stopped, setStopped] = useState(false);
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
    // Keep the previous panel mounted during background refresh.
    busyRef.current = true;
    apiGetQosRuntime().then(
      (res) => {
        if (cancelled || !mountedRef.current) return;
        busyRef.current = false;
        setRuntime(res);
        setStopped(false);
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
        setRuntime(null);
        // 409 = el despacho productivo no está corriendo (p. ej. backend
        // arrancado sin lifespan completo o pipeline detenido). No es un fallo.
        setStopped(apiErr?.status === 409);
        setFailed(apiErr?.status !== 409);
        setAuthBlocked(apiErr !== null && apiErr.isAuthError);
        setConfigMissing(apiErr?.code === 'NO_BASE_URL');
        setErrorMessage(
          apiErr?.status === 409
            ? null
            : err instanceof Error
              ? err.message
              : 'No se pudo cargar el estado del despacho.',
        );
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
      busyRef.current = false;
    };
  }, [attempt]);

  return {
    isLoading: loading,
    isAuthBlocked: authBlocked,
    isConfigMissing: configMissing,
    errorMessage,
    retry,
    status: loading ? 'loading' : failed ? 'error' : stopped ? 'stopped' : 'running',
    runtime,
  };
}
