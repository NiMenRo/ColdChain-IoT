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

/**
 * Suma de contadores con distinción «sin muestras» (null) frente a «cero real».
 * Usar en comparaciones experimentales: una ejecución sin muestras de un tipo
 * no debe presentarse como un 0 medido.
 */
export function sumMetricOrNull(samples: ExperimentMetric[], type: ExperimentMetricType): number | null {
  const vals = samples.filter(m => m.metric_type === type).map(m => m.value);
  if (vals.length === 0) return null;
  return vals.reduce((s, v) => s + v, 0);
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
      elapsedMin: (new Date(m.timestamp).getTime() - start) / 60000,
      value: m.value,
    }));
}

export function mergeLineSeries(
  a: { elapsedMin: number; value: number }[],
  b: { elapsedMin: number; value: number }[],
): { elapsedMin: number; withQos: number | null; withoutQos: number | null }[] {
  const keys = Array.from(new Set([...a.map(p => p.elapsedMin), ...b.map(p => p.elapsedMin)])).sort((x, y) => x - y);
  // Preserve even simultaneous observations (e.g. sibling sensors). A Map
  // from time to a single value silently discards all but the last sample.
  const group = (points: typeof a) => {
    const grouped = new Map<number, number[]>();
    for (const p of points) {
      const values = grouped.get(p.elapsedMin) ?? [];
      values.push(p.value);
      grouped.set(p.elapsedMin, values);
    }
    return grouped;
  };
  const mapA = group(a);
  const mapB = group(b);
  return keys.flatMap(elapsedMin => {
    const valuesA = mapA.get(elapsedMin) ?? [];
    const valuesB = mapB.get(elapsedMin) ?? [];
    return Array.from({ length: Math.max(valuesA.length, valuesB.length) }, (_, i) => ({
      elapsedMin,
      withQos: valuesA[i] ?? null,
      withoutQos: valuesB[i] ?? null,
    }));
  });
}

export { COUNTER_METRICS, LATENCY_METRICS };
