import { UserRole } from '../app/config/rbac';

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

// ─── Mock users (development only) ───────────────────────────────────────────
// These are replaced later by: POST /auth/login → { access_token, user }
const MOCK_USERS: Record<string, { password: string; user: User }> = {
  'admin@example.com': {
    password: 'demo1234',
    user: { id: 'u1', name: 'Ana García', email: 'admin@example.com', role: 'admin' },
  },
  'supervisor@example.com': {
    password: 'demo1234',
    user: { id: 'u2', name: 'Carlos López', email: 'supervisor@example.com', role: 'supervisor' },
  },
  'operador@example.com': {
    password: 'demo1234',
    user: { id: 'u3', name: 'María Rodríguez', email: 'operador@example.com', role: 'operador' },
  },
  'auditor@example.com': {
    password: 'demo1234',
    user: { id: 'u4', name: 'Jorge Sánchez', email: 'auditor@example.com', role: 'auditor' },
  },
};

const SESSION_KEY = 'coldchain_session';

const delay = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));

// ─── Auth functions ───────────────────────────────────────────────────────────
// Replace these with HTTP calls when FastAPI backend is ready:
//   login()        → POST /auth/login       { email, password } → { access_token, user }
//   logout()       → POST /auth/logout
//   getCurrentUser → GET  /auth/me          → User

export async function login(email: string, password: string): Promise<AuthResult> {
  await delay(800);
  const entry = MOCK_USERS[email.toLowerCase()];
  if (!entry || entry.password !== password) {
    return { success: false, error: 'Credenciales incorrectas. Verifica tu email y contraseña.' };
  }
  localStorage.setItem(SESSION_KEY, JSON.stringify(entry.user));
  return { success: true, user: entry.user };
}

export async function logout(): Promise<void> {
  await delay(150);
  localStorage.removeItem(SESSION_KEY);
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
