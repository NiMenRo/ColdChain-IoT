// Hook de auditoría (solo lectura).
//
// Patrón: AuditView → useAuditLogs → services/api/audit → apiFetch.
// Paginación server-side (page/per_page); los filtros de la vista aplican
// sobre la página traída porque el endpoint no expone filtros.
// outcome libre del backend → 'success' solo si es exactamente success.

import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../../services/api/client';
import { apiGetAuditLogs } from '../../services/api/audit';
import type { AuditLog } from '../types/audit';

export type SectionStatus = 'loading' | 'success' | 'empty' | 'error';

function toUiLog(r: {
  id: string;
  actor_user_id: string;
  action: string;
  resource: string;
  outcome: string;
  old_value: string | null;
  new_value: string | null;
  created_at: string;
}): AuditLog {
  return {
    id: r.id,
    timestamp: r.created_at,
    actor: r.actor_user_id,
    action: r.action as AuditLog['action'],
    resource: r.resource,
    result: r.outcome === 'success' ? 'success' : 'failure',
    old_value: r.old_value,
    new_value: r.new_value,
  };
}

export interface AuditLogsState {
  isLoading: boolean;
  isAuthBlocked: boolean;
  isForbidden: boolean;
  isConfigMissing: boolean;
  errorMessage: string | null;
  retry: () => void;
  status: SectionStatus;
  logs: AuditLog[];
  total: number;
}

export function useAuditLogs(page: number, perPage: number): AuditLogsState {
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [authBlocked, setAuthBlocked] = useState(false);
  const [forbidden, setForbidden] = useState(false);
  const [configMissing, setConfigMissing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [failed, setFailed] = useState(false);
  const [total, setTotal] = useState(0);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    apiGetAuditLogs({ page, per_page: perPage }).then(
      (res) => {
        if (cancelled) return;
        setLogs(res.results.map(toUiLog));
        setTotal(res.total);
        setFailed(false);
        setAuthBlocked(false);
        setForbidden(false);
        setConfigMissing(false);
        setErrorMessage(null);
        setLoading(false);
      },
      (err: unknown) => {
        if (cancelled) return;
        const apiErr = err instanceof ApiError ? err : null;
        setLogs([]);
        setTotal(0);
        setFailed(true);
        setAuthBlocked(apiErr !== null && apiErr.isAuthError && apiErr.status !== 403);
        setForbidden(apiErr?.status === 403);
        setConfigMissing(apiErr?.code === 'NO_BASE_URL');
        setErrorMessage(err instanceof Error ? err.message : 'No se pudo cargar la auditoría.');
        setLoading(false);
      },
    );

    return () => {
      cancelled = true;
    };
  }, [attempt, page, perPage]);

  return {
    isLoading: loading,
    isAuthBlocked: authBlocked,
    isForbidden: forbidden,
    isConfigMissing: configMissing,
    errorMessage,
    retry,
    status: loading ? 'loading' : failed ? 'error' : logs.length === 0 ? 'empty' : 'success',
    logs,
    total,
  };
}
