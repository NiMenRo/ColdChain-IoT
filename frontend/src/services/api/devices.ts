// Servicio de dominio: dispositivos (TSK-048/TSK-049).
//
// Contratos reales (backend/app/devices/api.py + schemas.py):
// - GET /devices → DeviceListResponse
// - GET /devices/{id} → DeviceDetailResponse { device, sensors }
// - POST /devices → DeviceDetailResponse (solo admin; 409 si el código duplica)
// - PUT /devices/{id}/sensors → DeviceDetailResponse (solo admin)
// Todos exigen autenticación Bearer.

import type { Device, DeviceFormData, SensorType } from '../../app/types/devices';
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

export interface DeviceDetailResponse {
  device: Device;
  sensors: SensorType[];
}

export async function apiGetDeviceDetail(deviceId: string): Promise<DeviceDetailResponse> {
  return apiFetch<DeviceDetailResponse>(`/devices/${encodeURIComponent(deviceId)}`);
}

export interface CreateDevicePayload {
  code: string;
  name: string;
  location: string;
  device_type: string;
  status: string;
  sensors: SensorType[];
}

export function toCreateDevicePayload(data: DeviceFormData): CreateDevicePayload {
  return {
    code: data.code.trim().toUpperCase(),
    name: data.name.trim(),
    location: data.location.trim(),
    device_type: data.device_type,
    status: data.status,
    sensors: [...data.sensors],
  };
}

export async function apiCreateDevice(payload: CreateDevicePayload): Promise<DeviceDetailResponse> {
  return apiFetch<DeviceDetailResponse>('/devices', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function apiReplaceDeviceSensors(deviceId: string, sensors: SensorType[]): Promise<DeviceDetailResponse> {
  return apiFetch<DeviceDetailResponse>(`/devices/${encodeURIComponent(deviceId)}/sensors`, {
    method: 'PUT',
    body: JSON.stringify({ sensors: [...sensors] }),
  });
}
