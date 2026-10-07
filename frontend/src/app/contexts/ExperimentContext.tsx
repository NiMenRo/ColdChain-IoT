import { createContext, useContext, useState, ReactNode } from 'react';
import {
  ExperimentMetric,
  ExperimentRun,
  ExperimentRunMeta,
  ExperimentScenario,
  SensorCondition,
} from '../types/experiments';
import {
  INITIAL_EXPERIMENT_METRICS,
  INITIAL_EXPERIMENT_RUNS,
  INITIAL_RUN_META,
  metricsForRun,
  seriesForRun,
} from '../data/experimentMocks';

interface ExperimentContextValue {
  runs: ExperimentRun[];
  metrics: ExperimentMetric[];
  runMeta: Record<string, ExperimentRunMeta>;
  activeRun: ExperimentRun | null;
  startRun: (input: { scenario: ExperimentScenario; sensorCondition: SensorCondition }) => ExperimentRun | null;
  finishRun: (id: string) => void;
}

const ExperimentContext = createContext<ExperimentContextValue | null>(null);

export function ExperimentProvider({ children }: { children: ReactNode }) {
  const [runs, setRuns] = useState<ExperimentRun[]>(INITIAL_EXPERIMENT_RUNS);
  const [metrics, setMetrics] = useState<ExperimentMetric[]>(INITIAL_EXPERIMENT_METRICS);
  const [runMeta, setRunMeta] = useState<Record<string, ExperimentRunMeta>>(INITIAL_RUN_META);

  const activeRun = runs.find(r => !r.finished_at) ?? null;

  function startRun({ scenario, sensorCondition }: { scenario: ExperimentScenario; sensorCondition: SensorCondition }): ExperimentRun | null {
    if (runs.some(r => !r.finished_at)) return null;
    const now = new Date().toISOString();
    const run: ExperimentRun = {
      id: crypto.randomUUID(),
      scenario,
      started_at: now,
      finished_at: null,
      config_snapshot: JSON.stringify({ ingest_hz: 2, devices: 6, duration_s: null, source: 'prototype_local' }),
    };
    setRuns(prev => [run, ...prev]);
    setRunMeta(prev => ({ ...prev, [run.id]: { sensorCondition, scope: 'all' } }));
    setMetrics(prev => [...prev, ...metricsForRun(run, seriesForRun(scenario, sensorCondition))]);
    return run;
  }

  function finishRun(id: string) {
    const now = new Date().toISOString();
    setRuns(prev => prev.map(r => (r.id === id && !r.finished_at ? { ...r, finished_at: now } : r)));
  }

  return (
    <ExperimentContext.Provider value={{ runs, metrics, runMeta, activeRun, startRun, finishRun }}>
      {children}
    </ExperimentContext.Provider>
  );
}

export function useExperiments(): ExperimentContextValue {
  const ctx = useContext(ExperimentContext);
  if (!ctx) throw new Error('useExperiments must be used inside <ExperimentProvider>');
  return ctx;
}
