// Cliente HTTP centralizado (TSK-048).
//
// Única frontera HTTP del frontend: View → Hook → services/api/* → apiFetch.
// - Base URL exclusivamente desde VITE_API_BASE_URL (ver .env.example).
// - Adjunta `Authorization: Bearer <token>` solo cuando existe un token real
//   en localStorage (`coldchain_token`). La integración de autenticación real
//   (login JWT) pertenece a otra tarea: aquí NO se inventa ni quema ningún token.
// - Sin Axios, sin WebSocket/MQTT, sin polling.

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string | undefined;

/** Clave donde una futura integración de auth guardará el JWT real. */
export const AUTH_TOKEN_KEY = 'coldchain_token';

export function getApiBaseUrl(): string | undefined {
  return API_BASE_URL;
}

/** Devuelve el Bearer real si existe; nunca genera uno falso. */
export function getAuthToken(): string | null {
  if (typeof window === 'undefined' || !window.localStorage) return null;
  const raw = window.localStorage.getItem(AUTH_TOKEN_KEY);
  if (!raw) return null;
  const token = raw.trim();
  return token.length > 0 ? token : null;
}

export type ApiErrorCode = 'NO_BASE_URL' | 'NETWORK' | 'HTTP';

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status?: number;

  constructor(code: ApiErrorCode, message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }

  get isAuthError(): boolean {
    return this.status === 401 || this.status === 403;
  }
}

function joinUrl(base: string, path: string): string {
  const cleanBase = base.replace(/\/+$/, '');
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${cleanBase}${cleanPath}`;
}

function httpMessage(status: number): string {
  if (status === 401) return 'No autenticado: se requiere iniciar sesión contra el backend (integración de autenticación pendiente).';
  if (status === 403) return 'Sin permiso para este recurso (verifique el rol del usuario).';
  if (status === 404) return 'Recurso no encontrado en la API.';
  if (status >= 500) return 'Error interno del backend.';
  return `La API respondió con estado ${status}.`;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getApiBaseUrl();
  if (!base || base.trim().length === 0) {
    throw new ApiError(
      'NO_BASE_URL',
      'VITE_API_BASE_URL no está configurada. Defina la URL del backend en un archivo .env local.',
    );
  }

  const token = getAuthToken();
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (init?.headers) {
    const extra = init.headers as Record<string, string>;
    for (const key of Object.keys(extra)) headers[key] = extra[key];
  }
  if (token) headers.Authorization = `Bearer ${token}`;
  if (init?.body !== undefined && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  let response: Response;
  try {
    response = await fetch(joinUrl(base, path), { ...init, headers });
  } catch (err) {
    throw new ApiError('NETWORK', 'No se pudo alcanzar el backend. Verifique que la API esté en ejecución y la URL configurada.', undefined);
  }

  if (!response.ok) {
    throw new ApiError('HTTP', httpMessage(response.status), response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
