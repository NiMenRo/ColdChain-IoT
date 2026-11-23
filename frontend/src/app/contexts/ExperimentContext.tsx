import { createContext, useCallback, useContext, useEffect, useState, useRef, ReactNode } from 'react';
import {
  ExperimentAnalysis,
  ExperimentRun,
  ExperimentRunMeta,
  ExperimentScenario,
  SensorCondition,
} from '../types/experiments';
import { ApiError } from '../../services/api/client';
import {
  apiFinishExperimentRun,
  loadExperimentRuns,
  apiGetRunAnalysis,
  apiStartExperimentRun,
} from '../../services/api/experiments';

export type SectionStatus = 'loading' | 'success' | 'empty' | 'error';

interface ExperimentContextValue {
  runs: ExperimentRun[];
  analyses: Record<string, ExperimentAnalysis>;
  intervalAnalyses: Record<string, Record<number, ExperimentAnalysis>>;
  analysisErrors: Record<string, string>;
  runMeta: Record<string, ExperimentRunMeta>;
  activeRun: ExperimentRun | null;
  status: SectionStatus;
  isAuthBlocked: boolean;
  isConfigMissing: boolean;
  errorMessage: string | null;
  retry: () => void;
  startRun: (input: { scenario: ExperimentScenario; sensorCondition: SensorCondition }) => Promise<{ run: ExperimentRun | null; error?: string }>;
  finishRun: (id: string) => Promise<{ ok: boolean; pending?: boolean; error?: string }>;
  fetchAnalysis: (runId: string, bucketSeconds?: number) => Promise<void>;
}

const ExperimentContext = createContext<ExperimentContextValue | null>(null);

function toErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return 'La ejecución no se pudo cerrar por un conflicto. Actualice el estado e intente de nuevo.';
    if (err.status === 403) return 'Sin permiso: iniciar/finalizar ejecuciones requiere rol administrador.';
    if (err.status === 404) return 'La ejecución ya no existe en el backend.';
    if (err.status === 400) return 'Escenario inválido para el backend.';
    return err.message;
  }
  return fallback;
}

export function ExperimentProvider({ children }: { children: ReactNode }) {
  const [runs, setRuns] = useState<ExperimentRun[]>([]);
  const [analyses, setAnalyses] = useState<Record<string, ExperimentAnalysis>>({});
  const [intervalAnalyses, setIntervalAnalyses] = useState<Record<string, Record<number, ExperimentAnalysis>>>({});
  const [analysisErrors, setAnalysisErrors] = useState<Record<string, string>>({});
  const pending = useRef<Partial<Record<string, Promise<void>>>>({});
  const pendingWidths = useRef<Partial<Record<string, number | undefined>>>({});
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  // Metadata local optimista; la condición también queda en config_snapshot.
  // Si ambas fuentes faltan, la UI no inventa una condición.
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

    loadExperimentRuns().then(
      (res) => {
        if (cancelled) return;
        setRuns(res);
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
        setAnalyses({});
        setIntervalAnalyses({});
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
  useEffect(() => {
    if (!activeRun) return;
    const timer = window.setInterval(() => {
      void loadExperimentRuns().then((fresh) => {
        if (mounted.current) setRuns(fresh);
      }).catch(() => {});
    }, 10000);
    return () => window.clearInterval(timer);
  }, [activeRun?.id]);

  const fetchAnalysis = useCallback(function loadAnalysis(runId: string, bucketSeconds?: number): Promise<void> {
    const existing = pending.current[runId];
    if (existing) {
      if (pendingWidths.current[runId] === bucketSeconds) return existing;
      // Serialize differing resolutions so an older response cannot overwrite
      // the new selection. Requests at the same resolution still share work.
      return existing.catch(() => {}).then(() => loadAnalysis(runId, bucketSeconds));
    }
    pendingWidths.current[runId] = bucketSeconds;
    const request = apiGetRunAnalysis(runId, bucketSeconds).then(report => {
      if (report.run_id !== runId) throw new Error('La respuesta no corresponde a la prueba seleccionada.');
      if (bucketSeconds !== undefined && report.bucket_seconds !== bucketSeconds) {
        throw new Error('La duración de la prueba cambió. Actualice las estadísticas para comparar el mismo intervalo.');
      }
      if (!mounted.current) return;
      setAnalyses(prev => ({ ...prev, [runId]: report }));
      if (bucketSeconds !== undefined) {
        setIntervalAnalyses(prev => ({ ...prev, [runId]: { ...prev[runId], [bucketSeconds]: report } }));
      }
      setAnalysisErrors(prev => { const next = { ...prev }; delete next[runId]; return next; });
    }).catch((err: unknown) => {
      if (mounted.current) {
        setAnalyses(prev => { const next = { ...prev }; delete next[runId]; return next; });
        if (bucketSeconds !== undefined) {
          setIntervalAnalyses(prev => {
            const reports = { ...prev[runId] };
            delete reports[bucketSeconds];
            return { ...prev, [runId]: reports };
          });
        }
        setAnalysisErrors(prev => ({ ...prev, [runId]: 'No se pudieron cargar las estadísticas. Intente nuevamente.' }));
      }
      throw err;
    }).finally(() => { delete pending.current[runId]; delete pendingWidths.current[runId]; });
    pending.current[runId] = request;
    return request;
  }, []);

  async function startRun({ scenario, sensorCondition }: { scenario: ExperimentScenario; sensorCondition: SensorCondition }) {
    if (runs.some((r) => !r.finished_at)) {
      return { run: null, error: 'Ya hay una ejecución activa. Finalícela antes de iniciar otra.' };
    }
    try {
      // La condición viaja persistida en config_snapshot para que la etiqueta
      // sobreviva recargas y sesiones (el backend la guarda tal cual).
      const run = await apiStartExperimentRun(scenario, { sensor_condition: sensorCondition });
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
      if (!run.finished_at) return { ok: true, pending: true };
      try {
        // A request started before closing must not replace the final snapshot.
        await pending.current[id]?.catch(() => {});
        await fetchAnalysis(id);
      } catch {
        // Métricas opcionales tras el cierre: el run ya quedó finalizado.
      }
      return { ok: true, pending: false };
    } catch (err) {
      return { ok: false, error: toErrorMessage(err, 'No se pudo finalizar la ejecución.') };
    }
  }

  return (
    <ExperimentContext.Provider
      value={{
        runs,
        analyses,
        intervalAnalyses,
        analysisErrors,
        runMeta,
        activeRun,
        status: loading ? 'loading' : failed ? 'error' : runs.length === 0 ? 'empty' : 'success',
        isAuthBlocked: authBlocked,
        isConfigMissing: configMissing,
        errorMessage,
        retry,
        startRun,
        finishRun,
        fetchAnalysis,
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
