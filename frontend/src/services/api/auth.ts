// Servicio de autenticación contra la API real (TSK-053).
//
// Contratos reales (backend/app/auth/api.py + schemas.py):
// - POST /auth/login {email, password} → {access_token, token_type, expires_in} (401 credenciales inválidas)
// - GET  /auth/me → {id, email, name, role, is_active, created_at} (401 token ausente/inválido/expirado)
// - POST /auth/password-reset/request {email} → respuesta genérica (202)
// - POST /auth/password-reset/confirm {token, new_password} → contraseña actualizada
// No existe POST /auth/logout en el backend: salir es limpiar el token local.

import { apiFetch } from './client';

export interface LoginTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface CurrentUserResponse {
  id: string;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export async function apiLogin(email: string, password: string): Promise<LoginTokenResponse> {
  return apiFetch<LoginTokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export async function apiGetMe(): Promise<CurrentUserResponse> {
  return apiFetch<CurrentUserResponse>('/auth/me');
}

export async function apiLogout(): Promise<void> {
  await apiFetch<void>('/auth/logout', { method: 'POST' });
}

export async function apiRequestPasswordReset(email: string): Promise<{ message: string }> {
  return apiFetch<{ message: string }>('/auth/password-reset/request', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

export async function apiConfirmPasswordReset(
  token: string,
  newPassword: string,
): Promise<{ message: string }> {
  return apiFetch<{ message: string }>('/auth/password-reset/confirm', {
    method: 'POST',
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}
