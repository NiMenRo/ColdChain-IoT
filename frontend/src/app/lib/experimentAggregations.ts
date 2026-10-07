import {
  COUNTER_METRICS,
  ExperimentMetric,
  ExperimentMetricType,
  ExperimentRun,
  LATENCY_METRICS,
} from '../types/experiments';

/**
 * Agregaciones locales del prototipo (no hay percentiles en el contrato).
 *
 * - Contadores (`messages_*`, `readings_persisted`, `alerts_generated`):
 *   cada muestra se trata como incremento; el valor mostrado es la SUMA.
 * - Latencias (`ingest_to_*_ms`): PROMEDIO y MÁXIMO de las muestras.
 * - Backlog: PROMEDIO y MÁXIMO de las muestras (profundidad de cola).
 */
export function metricsForRun(all: ExperimentMetric[], runId: string): ExperimentMetric[] {
  return all.filter(m => m.run_id === runId);
}

export function sumMetric(samples: ExperimentMetric[], type: ExperimentMetricType): number {
  return samples.filter(m => m.metric_type === type).reduce((s, m) => s + m.value, 0);
}

export function avgMetric(samples: ExperimentMetric[], type: ExperimentMetricType): number | null {
  const vals = samples.filter(m => m.metric_type === type).map(m => m.value);
  if (vals.length === 0) return null;
  return vals.reduce((s, v) => s + v, 0) / vals.length;
}

export function maxMetric(samples: ExperimentMetric[], type: ExperimentMetricType): number | null {
  const vals = samples.filter(m => m.metric_type === type).map(m => m.value);
  if (vals.length === 0) return null;
  return Math.max(...vals);
}

export function runDurationMs(run: ExperimentRun, now = Date.now()): number {
  const end = run.finished_at ? new Date(run.finished_at).getTime() : now;
  return Math.max(0, end - new Date(run.started_at).getTime());
}

export function formatDuration(ms: number): string {
  const totalMin = Math.round(ms / 60000);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  if (h <= 0) return `${m} min`;
  return `${h} h ${m} min`;
}

export function delta(a: number | null, b: number | null): number | null {
  if (a === null || b === null) return null;
  return a - b;
}

/** Δ % = (a - b) / b * 100. Null si b es 0 o no hay datos. */
export function deltaPercent(a: number | null, b: number | null): number | null {
  if (a === null || b === null || b === 0) return null;
  return ((a - b) / b) * 100;
}

export function seriesByElapsed(
  samples: ExperimentMetric[],
  type: ExperimentMetricType,
  startedAt: string,
): { elapsedMin: number; value: number }[] {
  const start = new Date(startedAt).getTime();
  return samples
    .filter(m => m.metric_type === type)
    .sort((x, y) => x.timestamp.localeCompare(y.timestamp))
    .map(m => ({
      elapsedMin: Math.round((new Date(m.timestamp).getTime() - start) / 60000),
      value: m.value,
    }));
}

export function mergeLineSeries(
  a: { elapsedMin: number; value: number }[],
  b: { elapsedMin: number; value: number }[],
): { elapsedMin: number; withQos: number | null; withoutQos: number | null }[] {
  const keys = Array.from(new Set([...a.map(p => p.elapsedMin), ...b.map(p => p.elapsedMin)])).sort((x, y) => x - y);
  const mapA = new Map(a.map(p => [p.elapsedMin, p.value]));
  const mapB = new Map(b.map(p => [p.elapsedMin, p.value]));
  return keys.map(elapsedMin => ({
    elapsedMin,
    withQos: mapA.has(elapsedMin) ? mapA.get(elapsedMin)! : null,
    withoutQos: mapB.has(elapsedMin) ? mapB.get(elapsedMin)! : null,
  }));
}

export { COUNTER_METRICS, LATENCY_METRICS };
