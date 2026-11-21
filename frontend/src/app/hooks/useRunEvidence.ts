import { useCallback, useEffect, useRef, useState } from 'react';
import { apiGetRunEvidence } from '../../services/api/experiments';
import { ApiError } from '../../services/api/client';
import type { ExperimentEvidence, ExperimentRun } from '../types/experiments';
import { usePolling } from './usePolling';

export function shouldPollEvidence(run: ExperimentRun | null, data: ExperimentEvidence | null) {
  return !!run && data?.status !== 'final' && (!run.finished_at || data?.status === 'provisional');
}

/** No cached report from another run, and no overlapping/stale HTTP responses. */
export function useRunEvidence(run: ExperimentRun | null) {
  const [data, setData] = useState<ExperimentEvidence | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [authBlocked, setAuthBlocked] = useState(false);
  const generation = useRef(0);
  const busy = useRef(false);
  const runId = run?.id;

  const load = useCallback(async () => {
    if (!runId || busy.current) return;
    const token = generation.current;
    busy.current = true;
    try {
      const report = await apiGetRunEvidence(runId);
      if (token !== generation.current) return;
      if (report.run_id !== runId) throw new Error('La evidencia no corresponde a la ejecución seleccionada.');
      setData(report);
      setError(null);
      setAuthBlocked(false);
    } catch (err) {
      if (token !== generation.current) return;
      setData(null);
      setError(err instanceof Error ? err.message : 'No se pudo cargar la evidencia.');
      setAuthBlocked(err instanceof ApiError && err.isAuthError);
    } finally {
      if (token === generation.current) {
        busy.current = false;
        setLoading(false);
      }
    }
  }, [runId]);

  useEffect(() => {
    generation.current += 1;
    busy.current = false;
    setData(null);
    setError(null);
    setAuthBlocked(false);
    setLoading(!!runId);
    void load();
    return () => { generation.current += 1; };
  }, [runId, run?.finished_at, load]);

  usePolling(
    !authBlocked && shouldPollEvidence(run, data),
    8000, () => { void load(); }, busy,
  );
  return {
    data: data?.run_id === runId ? data : null,
    error, loading, retry: () => { setLoading(true); void load(); },
  };
}
