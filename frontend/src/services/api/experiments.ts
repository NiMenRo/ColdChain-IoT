import { apiFetch } from './client';

export async function apiCreateExperimentRun(_payload: { scenario: string; config_snapshot: string }) {
  // Previamente: POST /experiment-runs
  return apiFetch('/experiment-runs', { method: 'POST' });
}

export async function apiGetExperimentRuns() {
  // Previamente: GET /experiment-runs
  return apiFetch('/experiment-runs');
}
