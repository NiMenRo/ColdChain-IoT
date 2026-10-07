// Placeholder del servicio de autenticación contra API real.
// Hoy authService.ts sigue usando mock/localStorage.
import { apiFetch } from './client';

export async function apiLogin(_email: string, _password: string) {
  // Previamente: POST /auth/login
  return apiFetch('/auth/login', { method: 'POST' });
}

export async function apiGetMe() {
  // Previamente: GET /auth/me
  return apiFetch('/auth/me');
}
