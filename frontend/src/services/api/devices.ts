// Servicio de dominio: dispositivos (TSK-048).
//
// Contrato real: GET /devices → DeviceListResponse
// (backend/app/devices/api.py + schemas.py). Requiere autenticación Bearer.

import type { Device } from '../../app/types/devices';
import { apiFetch } from './client';

export interface DeviceListResponse {
  total: number;
  page: number;
  per_page: number;
  count: number;
  results: Device[];
}

export async function apiGetDevices(params?: { page?: number; per_page?: number }): Promise<DeviceListResponse> {
  const qs = new URLSearchParams();
  qs.set('page', String(params?.page ?? 1));
  qs.set('per_page', String(params?.per_page ?? 100));
  return apiFetch<DeviceListResponse>(`/devices?${qs.toString()}`);
}
