import type { ExperimentRun, ExperimentRunMeta, SensorCondition } from '../types/experiments';

export type RunCondition = SensorCondition | 'unregistered';
export const CONDITION_LABELS: Record<RunCondition, string> = {
  normal: 'Sensores normales', altered: 'Sensores alterados', unregistered: 'Condición no registrada',
};

export function runCondition(run: ExperimentRun, meta: Record<string, ExperimentRunMeta>): RunCondition {
  if (meta[run.id]) return meta[run.id].sensorCondition;
  try {
    const condition = JSON.parse(run.config_snapshot ?? '{}').sensor_condition;
    if (condition === 'normal') return 'normal';
    if (condition === 'altered' || condition === 'critica') return 'altered';
  } catch { /* Missing metadata stays unknown, never a fabricated condition. */ }
  return 'unregistered';
}

export function suggestedCondition(runs: ExperimentRun[], meta: Record<string, ExperimentRunMeta>): SensorCondition {
  const sorted = [...runs].filter(run => runCondition(run, meta) !== 'unregistered')
    .sort((a, b) => b.started_at.localeCompare(a.started_at));
  for (const run of sorted) {
    const condition = runCondition(run, meta);
    if (condition !== 'unregistered' && sorted.some(other => other.finished_at && other.scenario !== run.scenario
        && runCondition(other, meta) === condition) && run.finished_at) return condition;
  }
  return sorted[0] && runCondition(sorted[0], meta) === 'altered' ? 'altered' : 'normal';
}
