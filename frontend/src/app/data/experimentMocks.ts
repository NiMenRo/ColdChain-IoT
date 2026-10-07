import {
  ExperimentMetric,
  ExperimentMetricType,
  ExperimentRun,
  ExperimentRunMeta,
  ExperimentScenario,
  SensorCondition,
} from '../types/experiments';

/**
 * Series deterministas por escenario. WITHOUT_QOS no incluye métricas de
 * clasificación/prioridad/colas: esas estructuras no existen en ese escenario.
 */
const SERIES: Record<ExperimentScenario, Record<ExperimentMetricType, number[]>> = {
  WITH_QOS: {
    messages_received:    [92, 88, 95, 90, 94, 91, 89, 93],
    messages_invalid:     [2, 1, 3, 1, 2, 2, 1, 2],
    readings_persisted:   [88, 85, 90, 86, 91, 87, 86, 89],
    alerts_generated:     [1, 0, 2, 1, 1, 0, 1, 1],
    backlog:              [3, 4, 2, 5, 3, 4, 2, 3],
    ingest_to_persist_ms: [48, 52, 45, 58, 50, 47, 53, 49],
    ingest_to_alert_ms:   [62, 70, 58, 75, 66, 61, 72, 64],
  },
  WITHOUT_QOS: {
    messages_received:    [90, 87, 93, 88, 91, 86, 89, 92],
    messages_invalid:     [4, 5, 3, 6, 4, 5, 4, 5],
    readings_persisted:   [72, 68, 74, 65, 70, 63, 69, 71],
    alerts_generated:     [2, 3, 2, 4, 3, 2, 3, 3],
    backlog:              [28, 34, 41, 38, 46, 42, 39, 44],
    ingest_to_persist_ms: [210, 245, 198, 268, 232, 255, 221, 248],
    ingest_to_alert_ms:   [280, 310, 265, 340, 295, 325, 288, 318],
  },
};

function ticks(startedAt: string, count: number, stepMs: number): string[] {
  const start = new Date(startedAt).getTime();
  return Array.from({ length: count }, (_, i) => new Date(start + i * stepMs).toISOString());
}

export function metricsForRun(run: ExperimentRun, series: Record<ExperimentMetricType, number[]>): ExperimentMetric[] {
  const points = series.messages_received.length;
  const end = run.finished_at ?? new Date(new Date(run.started_at).getTime() + (points - 1) * 15 * 60 * 1000).toISOString();
  const span = new Date(end).getTime() - new Date(run.started_at).getTime();
  const step = points > 1 ? span / (points - 1) : 0;
  const times = ticks(run.started_at, points, step);
  const types = Object.keys(series) as ExperimentMetricType[];
  const out: ExperimentMetric[] = [];
  types.forEach(type => {
    series[type].forEach((value, i) => {
      out.push({
        id: `${run.id}-${type}-${i}`,
        run_id: run.id,
        metric_type: type,
        value,
        timestamp: times[i],
      });
    });
  });
  return out;
}

export const INITIAL_EXPERIMENT_RUNS: ExperimentRun[] = [
  {
    id: '3f2a9c1e-7b14-4d6a-9e20-aa11bb22cc01',
    scenario: 'WITH_QOS',
    started_at: '2026-10-01T08:00:00.000Z',
    finished_at: '2026-10-01T10:00:00.000Z',
    config_snapshot: JSON.stringify({ ingest_hz: 2, devices: 6, duration_s: 7200 }),
  },
  {
    id: '8c44d0b2-1a9f-4e33-b712-dd33ee44ff02',
    scenario: 'WITHOUT_QOS',
    started_at: '2026-10-01T11:00:00.000Z',
    finished_at: '2026-10-01T13:00:00.000Z',
    config_snapshot: JSON.stringify({ ingest_hz: 2, devices: 6, duration_s: 7200 }),
  },
  {
    id: 'a19b6e70-c5d8-4f21-8a44-112233445503',
    scenario: 'WITH_QOS',
    started_at: '2026-10-03T09:00:00.000Z',
    finished_at: '2026-10-03T10:30:00.000Z',
    config_snapshot: JSON.stringify({ ingest_hz: 1, devices: 6, duration_s: 5400 }),
  },
  {
    id: 'b27c8f81-d6e9-4022-9b55-223344556604',
    scenario: 'WITHOUT_QOS',
    started_at: '2026-10-03T11:00:00.000Z',
    finished_at: '2026-10-03T12:30:00.000Z',
    config_snapshot: JSON.stringify({ ingest_hz: 1, devices: 6, duration_s: 5400 }),
  },
  {
    id: 'c38d9a92-e7f0-4133-ac66-334455667705',
    scenario: 'WITH_QOS',
    started_at: '2026-10-05T08:30:00.000Z',
    finished_at: null,
    config_snapshot: JSON.stringify({ ingest_hz: 2, devices: 6, duration_s: null }),
  },
];


const ALTERED_FACTORS: Record<ExperimentMetricType, number> = {
  messages_received: 1.0,
  messages_invalid: 4.0,
  readings_persisted: 0.7,
  alerts_generated: 3.5,
  backlog: 8.0,
  ingest_to_persist_ms: 2.5,
  ingest_to_alert_ms: 2.5,
};

/**
 * Variación determinista SOLO VISUAL para la demo: mismos tipos de métrica,
 * valores escalados para reflejar lecturas fuera de rango (más inválidos,
 * alertas, backlog y latencias). NO representa un resultado del backend.
 */
export function seriesForRun(
  scenario: ExperimentScenario,
  condition: SensorCondition,
): Record<ExperimentMetricType, number[]> {
  const base = SERIES[scenario];
  if (condition === 'normal') return base;
  const out = {} as Record<ExperimentMetricType, number[]>;
  (Object.keys(base) as ExperimentMetricType[]).forEach(type => {
    out[type] = base[type].map(v => Math.max(0, Math.round(v * ALTERED_FACTORS[type])));
  });
  return out;
}

export const INITIAL_RUN_META: Record<string, ExperimentRunMeta> = {
  '3f2a9c1e-7b14-4d6a-9e20-aa11bb22cc01': { sensorCondition: 'normal',  scope: 'all' },
  '8c44d0b2-1a9f-4e33-b712-dd33ee44ff02': { sensorCondition: 'normal',  scope: 'all' },
  'a19b6e70-c5d8-4f21-8a44-112233445503': { sensorCondition: 'altered', scope: 'all' },
  'b27c8f81-d6e9-4022-9b55-223344556604': { sensorCondition: 'altered', scope: 'all' },
  'c38d9a92-e7f0-4133-ac66-334455667705': { sensorCondition: 'normal',  scope: 'all' },
};

export const INITIAL_EXPERIMENT_METRICS: ExperimentMetric[] = INITIAL_EXPERIMENT_RUNS.flatMap(run => {
  const meta = INITIAL_RUN_META[run.id];
  const base = seriesForRun(run.scenario, meta?.sensorCondition ?? 'normal');
  if (!run.finished_at) {
    const partial: Record<ExperimentMetricType, number[]> = {
      messages_received:    base.messages_received.slice(0, 4),
      messages_invalid:     base.messages_invalid.slice(0, 4),
      readings_persisted:   base.readings_persisted.slice(0, 4),
      alerts_generated:     base.alerts_generated.slice(0, 4),
      backlog:              base.backlog.slice(0, 4),
      ingest_to_persist_ms: base.ingest_to_persist_ms.slice(0, 4),
      ingest_to_alert_ms:   base.ingest_to_alert_ms.slice(0, 4),
    };
    return metricsForRun(run, partial);
  }
  return metricsForRun(run, base);
});
