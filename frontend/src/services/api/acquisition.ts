import { apiFetch } from './client';

export interface AcquisitionStatus {
  /** null: the backend has not initialized its MQTT client. */
  connected: boolean | null;
}

export function apiGetAcquisitionStatus(): Promise<AcquisitionStatus> {
  return apiFetch<AcquisitionStatus>('/acquisition/status');
}
