// Servicio de dominio: gestión de usuarios (solo admin).
//
// Contratos reales (backend/app/users/api.py + schemas.py, TSK-055):
// - GET   /users → {total,page,per_page,count,results[{id,name,email,role,is_active,created_at}]}
// - POST  /users {name,email,password,role,is_active?} → UserResponse (409 email duplicado)
// - PATCH /users/{id} {name?,email?,role?,is_active?} → UserResponse
//     (403 auto-cambio de rol propio, identidad system protegida, 404/409)
// - POST  /users/{id}/password {new_password} → {message, id}
// Todo exige rol admin (401/403). Sin self-service.

import { apiFetch } from './client';

export interface ManagedUserRecord {
  id: string;
  name: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface UserListResponse {
  total: number;
  page: number;
  per_page: number;
  count: number;
  results: ManagedUserRecord[];
}

export async function apiGetUsers(params?: {
  page?: number;
  per_page?: number;
}): Promise<UserListResponse> {
  const qs = new URLSearchParams();
  qs.set('page', String(params?.page ?? 1));
  qs.set('per_page', String(params?.per_page ?? 100));
  return apiFetch<UserListResponse>(`/users?${qs.toString()}`);
}

export interface CreateUserPayload {
  name: string;
  email: string;
  password: string;
  role: string;
  is_active?: boolean;
}

export async function apiCreateUser(payload: CreateUserPayload): Promise<ManagedUserRecord> {
  return apiFetch<ManagedUserRecord>('/users', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export interface UpdateUserPayload {
  name?: string;
  email?: string;
  role?: string;
  is_active?: boolean;
}

export async function apiUpdateUser(userId: string, payload: UpdateUserPayload): Promise<ManagedUserRecord> {
  return apiFetch<ManagedUserRecord>(`/users/${encodeURIComponent(userId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}
