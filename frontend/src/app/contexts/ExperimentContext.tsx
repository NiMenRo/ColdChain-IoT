import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from 'react';
import {
  ExperimentMetric,
  ExperimentRun,
  ExperimentRunMeta,
  ExperimentScenario,
  SensorCondition,
} from '../types/experiments';
import { ApiError } from '../../services/api/client';
import {
  apiFinishExperimentRun,
  apiGetExperimentRuns,
  apiGetRunMetrics,
  apiStartExperimentRun,
} from '../../services/api/experiments';

export type SectionStatus = 'loading' | 'success' | 'empty' | 'error';

interface ExperimentContextValue {
  runs: ExperimentRun[];
  metrics: ExperimentMetric[];
  runMeta: Record<string, ExperimentRunMeta>;
  activeRun: ExperimentRun | null;
  status: SectionStatus;
  isAuthBlocked: boolean;
  isConfigMissing: boolean;
  errorMessage: string | null;
  retry: () => void;
  startRun: (input: { scenario: ExperimentScenario; sensorCondition: SensorCondition }) => Promise<{ run: ExperimentRun | null; error?: string }>;
  finishRun: (id: string) => Promise<{ ok: boolean; error?: string }>;
  fetchMetrics: (runId: string) => Promise<void>;
}

const ExperimentContext = createContext<ExperimentContextValue | null>(null);

function toErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return 'Ya hay una ejecución activa en el backend. Finalícela antes de iniciar otra.';
    if (err.status === 403) return 'Sin permiso: iniciar/finalizar ejecuciones requiere rol administrador.';
    if (err.status === 404) return 'La ejecución ya no existe en el backend.';
    if (err.status === 400) return 'Escenario inválido para el backend.';
    return err.message;
  }
  return fallback;
}

export function ExperimentProvider({ children }: { children: ReactNode }) {
  const [runs, setRuns] = useState<ExperimentRun[]>([]);
  const [metrics, setMetrics] = useState<ExperimentMetric[]>([]);
  // sensorCondition es selección UI local (el backend no la persiste): solo
  // existe para runs iniciados en esta sesión. Los runs del backend sin meta
  // se muestran como condición no registrada, nunca inventada.
  const [runMeta, setRunMeta] = useState<Record<string, ExperimentRunMeta>>({});
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [authBlocked, setAuthBlocked] = useState(false);
  const [configMissing, setConfigMissing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    apiGetExperimentRuns({ page: 1, per_page: 50 }).then(
      (res) => {
        if (cancelled) return;
        setRuns(res.results);
        setFailed(false);
        setAuthBlocked(false);
        setConfigMissing(false);
        setErrorMessage(null);
        setLoading(false);
      },
      (err: unknown) => {
        if (cancelled) return;
        const apiErr = err instanceof ApiError ? err : null;
        setRuns([]);
        setMetrics([]);
        setFailed(true);
        setAuthBlocked(apiErr !== null && apiErr.isAuthError);
        setConfigMissing(apiErr?.code === 'NO_BASE_URL');
        setErrorMessage(err instanceof Error ? err.message : 'No se pudieron cargar las ejecuciones.');
        setLoading(false);
      },
    );

    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const activeRun = runs.find((r) => !r.finished_at) ?? null;

  const fetchMetrics = useCallback(async (runId: string) => {
    const res = await apiGetRunMetrics(runId, { page: 1, per_page: 100 });
    const incoming = res.results;
    setMetrics((prev) => {
      const known = new Set(prev.map((m) => m.id));
      return [...prev, ...incoming.filter((m) => !known.has(m.id))];
    });
  }, []);

  async function startRun({ scenario, sensorCondition }: { scenario: ExperimentScenario; sensorCondition: SensorCondition }) {
    if (runs.some((r) => !r.finished_at)) {
      return { run: null, error: 'Ya hay una ejecución activa. Finalícela antes de iniciar otra.' };
    }
    try {
      const run = await apiStartExperimentRun(scenario);
      setRuns((prev) => [run, ...prev]);
      setRunMeta((prev) => ({ ...prev, [run.id]: { sensorCondition, scope: 'all' } }));
      return { run };
    } catch (err) {
      return { run: null, error: toErrorMessage(err, 'No se pudo iniciar la ejecución.') };
    }
  }

  async function finishRun(id: string) {
    try {
      const run = await apiFinishExperimentRun(id);
      setRuns((prev) => prev.map((r) => (r.id === id ? run : r)));
      try {
        await fetchMetrics(id);
      } catch {
        // Métricas opcionales tras el cierre: el run ya quedó finalizado.
      }
      return { ok: true };
    } catch (err) {
      return { ok: false, error: toErrorMessage(err, 'No se pudo finalizar la ejecución.') };
    }
  }

  return (
    <ExperimentContext.Provider
      value={{
        runs,
        metrics,
        runMeta,
        activeRun,
        status: loading ? 'loading' : failed ? 'error' : runs.length === 0 ? 'empty' : 'success',
        isAuthBlocked: authBlocked,
        isConfigMissing: configMissing,
        errorMessage,
        retry,
        startRun,
        finishRun,
        fetchMetrics,
      }}
    >
      {children}
    </ExperimentContext.Provider>
  );
}

export function useExperiments(): ExperimentContextValue {
  const ctx = useContext(ExperimentContext);
  if (!ctx) throw new Error('useExperiments must be used inside <ExperimentProvider>');
  return ctx;
}
