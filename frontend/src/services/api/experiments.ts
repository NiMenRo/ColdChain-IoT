// Servicio de dominio: corridas experimentales y métricas (solo lectura + control).
//
// Contratos reales (backend/app/experiments/api.py + schemas.py):
// - GET  /experiment-runs?scenario&page&per_page → {total,…,results[{id,scenario,started_at,finished_at,config_snapshot}]}
// - POST /experiment-runs {scenario, config_snapshot?} → 201 run (solo admin; 409 si hay run activo)
// - POST /experiment-runs/{id}/finish → run con finished_at (solo admin; 404)
// - GET  /experiment-runs/{id}/metrics?metric_type&page&per_page → {total,…,results[{id,run_id,metric_type,value,timestamp}]}
// Escenarios: WITH_QOS | WITHOUT_QOS. Métricas CHECK: messages_received,
// messages_invalid, readings_persisted, alerts_generated, backlog,
// ingest_to_persist_ms, ingest_to_alert_ms. Todo exige Bearer.

import type { ExperimentMetric, ExperimentRun, ExperimentScenario } from '../../app/types/experiments';
import { apiFetch } from './client';

export interface ExperimentRunListResponse {
  total: number;
  page: number;
  per_page: number;
  count: number;
  results: ExperimentRun[];
}

export async function apiGetExperimentRuns(params?: {
  scenario?: ExperimentScenario;
  page?: number;
  per_page?: number;
}): Promise<ExperimentRunListResponse> {
  const qs = new URLSearchParams();
  if (params?.scenario) qs.set('scenario', params.scenario);
  qs.set('page', String(params?.page ?? 1));
  qs.set('per_page', String(params?.per_page ?? 20));
  return apiFetch<ExperimentRunListResponse>(`/experiment-runs?${qs.toString()}`);
}

export async function apiStartExperimentRun(scenario: ExperimentScenario): Promise<ExperimentRun> {
  // Sin config_snapshot: el backend usa los umbrales del sistema (no secretos).
  return apiFetch<ExperimentRun>('/experiment-runs', {
    method: 'POST',
    body: JSON.stringify({ scenario }),
  });
}

export async function apiFinishExperimentRun(runId: string): Promise<ExperimentRun> {
  return apiFetch<ExperimentRun>(`/experiment-runs/${encodeURIComponent(runId)}/finish`, {
    method: 'POST',
  });
}

export interface ExperimentMetricListResponse {
  total: number;
  page: number;
  per_page: number;
  count: number;
  results: ExperimentMetric[];
}

export async function apiGetRunMetrics(
  runId: string,
  params?: { page?: number; per_page?: number },
): Promise<ExperimentMetricListResponse> {
  const qs = new URLSearchParams();
  qs.set('page', String(params?.page ?? 1));
  qs.set('per_page', String(params?.per_page ?? 100));
  return apiFetch<ExperimentMetricListResponse>(
    `/experiment-runs/${encodeURIComponent(runId)}/metrics?${qs.toString()}`,
  );
}
