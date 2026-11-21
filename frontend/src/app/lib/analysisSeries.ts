import type { AnalysisPoint, ExperimentRun } from '../types/experiments';

/** Same elapsed-time grid for both runs, targeting about 120 bins at most. */
export function comparisonInterval(runs: (ExperimentRun | null)[], now = Date.now()): number {
  const seconds = Math.max(0, ...runs.filter((r): r is ExperimentRun => !!r).map(run => {
    const duration = ((run.finished_at ? Date.parse(run.finished_at) : now) - Date.parse(run.started_at)) / 1000;
    return Number.isFinite(duration) ? Math.max(0, duration) : 0;
  }));
  return Math.max(0.1, Math.ceil(seconds / 120 * 1000) / 1000);
}

export function comparisonSeries(withQos: AnalysisPoint[], withoutQos: AnalysisPoint[]) {
  const rows = new Map<number, { elapsedMin: number; withPoint?: AnalysisPoint; withoutPoint?: AnalysisPoint }>();
  for (const [key, points] of [['withPoint', withQos], ['withoutPoint', withoutQos]] as const) {
    for (const point of points) {
      const row = rows.get(point.start_seconds) ?? { elapsedMin: point.elapsedMin };
      row[key] = point;
      rows.set(point.start_seconds, row);
    }
  }
  return [...rows.values()].sort((a, b) => a.elapsedMin - b.elapsedMin);
}
