import { UserRole } from '../app/config/rbac';
import { AUTH_TOKEN_KEY } from './api/client';
import { ApiError } from './api/client';
import { apiGetMe, apiLogin } from './api/auth';

// ─── Types ────────────────────────────────────────────────────────────────────
export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
}

interface AuthResult {
  success: boolean;
  user?: User;
  error?: string;
}

const SESSION_KEY = 'coldchain_session';

const VALID_ROLES: UserRole[] = ['admin', 'supervisor', 'operador', 'auditor'];

function toUserRole(role: string): UserRole | null {
  const normalized = role.trim().toLowerCase();
  return (VALID_ROLES as string[]).includes(normalized) ? (normalized as UserRole) : null;
}

function clearLocalSession(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(SESSION_KEY);
}

// ─── Auth functions (contratos reales del backend) ────────────────────────────
//   login()          → POST /auth/login { email, password } → guarda Bearer JWT
//                      + GET /auth/me para identidad/rol (nunca del cliente)
//   logout()         → limpieza local (el backend no expone POST /auth/logout)
//   getCurrentUser() → lectura sincrónica de sesión guardada (pintado inicial)
//   validateSession()→ GET /auth/me con el token guardado; 401 limpia la sesión

export async function login(email: string, password: string): Promise<AuthResult> {
  try {
    const { access_token } = await apiLogin(email.trim(), password);
    if (!access_token) {
      clearLocalSession();
      return { success: false, error: 'La API no devolvió un token válido.' };
    }
    localStorage.setItem(AUTH_TOKEN_KEY, access_token);
    const me = await apiGetMe();
    const role = toUserRole(me.role);
    if (!role) {
      clearLocalSession();
      return { success: false, error: `Rol no reconocido en la API: ${me.role}.` };
    }
    const user: User = { id: me.id, name: me.name, email: me.email, role };
    localStorage.setItem(SESSION_KEY, JSON.stringify(user));
    return { success: true, user };
  } catch (err) {
    clearLocalSession();
    if (err instanceof ApiError && err.status === 401) {
      return { success: false, error: 'Credenciales incorrectas. Verifica tu email y contraseña.' };
    }
    if (err instanceof ApiError && err.code === 'NO_BASE_URL') {
      return { success: false, error: 'API no configurada. Defina VITE_API_BASE_URL en un archivo .env local.' };
    }
    if (err instanceof ApiError && err.code === 'NETWORK') {
      return { success: false, error: 'No se pudo alcanzar la API. Verifique que el backend esté en ejecución.' };
    }
    return { success: false, error: 'No se pudo iniciar sesión. Intente de nuevo.' };
  }
}

export async function logout(): Promise<void> {
  clearLocalSession();
}

export function getCurrentUser(): User | null {
  const raw = localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

/** Valida el token guardado contra GET /auth/me. 401/ausencia → sesión limpia. */
export async function validateSession(): Promise<User | null> {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (!token || token.trim().length === 0) {
    clearLocalSession();
    return null;
  }
  try {
    const me = await apiGetMe();
    const role = toUserRole(me.role);
    if (!role) {
      clearLocalSession();
      return null;
    }
    const user: User = { id: me.id, name: me.name, email: me.email, role };
    localStorage.setItem(SESSION_KEY, JSON.stringify(user));
    return user;
  } catch {
    clearLocalSession();
    return null;
  }
}
