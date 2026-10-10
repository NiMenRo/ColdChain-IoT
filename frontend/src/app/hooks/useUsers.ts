// Hook de gestión de usuarios (solo admin).
//
// Patrón: UserManagementView → useUsers → services/api/users → apiFetch.
// Lista, crea y actualiza (incluye activar/desactivar vía PATCH is_active).
// Una sola carga al montar (+ refetch tras mutaciones y retry manual).

import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../../services/api/client';
import {
  apiCreateUser,
  apiGetUsers,
  apiUpdateUser,
  type CreateUserPayload,
  type ManagedUserRecord,
  type UpdateUserPayload,
} from '../../services/api/users';
import type { UserRole } from '../config/rbac';

export type SectionStatus = 'loading' | 'success' | 'empty' | 'error';

export interface ManagedUser {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  active: boolean;
  createdAt: string;
}

const VALID_ROLES: UserRole[] = ['admin', 'supervisor', 'operador', 'auditor'];

function toUiUser(r: ManagedUserRecord): ManagedUser | null {
  const role = r.role.trim().toLowerCase();
  if (!(VALID_ROLES as string[]).includes(role)) return null;
  return {
    id: r.id,
    name: r.name,
    email: r.email,
    role: role as UserRole,
    active: r.is_active,
    createdAt: r.created_at,
  };
}

function toErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return 'Ya existe un usuario con ese correo.';
    if (err.status === 403) return 'Sin permiso: revise que no edite su propio rol ni la identidad del sistema.';
    if (err.status === 404) return 'El usuario ya no existe.';
    if (err.status === 400) return 'Datos inválidos: revise el formulario.';
    return err.message;
  }
  return fallback;
}

export interface UsersState {
  isLoading: boolean;
  isAuthBlocked: boolean;
  isForbidden: boolean;
  isConfigMissing: boolean;
  errorMessage: string | null;
  retry: () => void;
  status: SectionStatus;
  users: ManagedUser[];
  createUser: (data: { name: string; email: string; role: UserRole; password: string }) => Promise<{ ok: boolean; error?: string }>;
  updateUser: (id: string, data: { name: string; email: string; role: UserRole }) => Promise<{ ok: boolean; error?: string }>;
  setActive: (id: string, active: boolean) => Promise<{ ok: boolean; error?: string }>;
}

export function useUsers(): UsersState {
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [authBlocked, setAuthBlocked] = useState(false);
  const [forbidden, setForbidden] = useState(false);
  const [configMissing, setConfigMissing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [failed, setFailed] = useState(false);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  const reload = useCallback(async () => {
    const res = await apiGetUsers({ page: 1, per_page: 100 });
    setUsers(res.results.map(toUiUser).filter((u): u is ManagedUser => u !== null));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    reload().then(
      () => {
        if (cancelled) return;
        setFailed(false);
        setAuthBlocked(false);
        setForbidden(false);
        setConfigMissing(false);
        setErrorMessage(null);
        setLoading(false);
      },
      (err: unknown) => {
        if (cancelled) return;
        const apiErr = err instanceof ApiError ? err : null;
        setUsers([]);
        setFailed(true);
        setAuthBlocked(apiErr !== null && apiErr.isAuthError && apiErr.status !== 403);
        setForbidden(apiErr?.status === 403);
        setConfigMissing(apiErr?.code === 'NO_BASE_URL');
        setErrorMessage(err instanceof Error ? err.message : 'No se pudieron cargar los usuarios.');
        setLoading(false);
      },
    );

    return () => {
      cancelled = true;
    };
  }, [attempt, reload]);

  const createUser = useCallback(async (data: { name: string; email: string; role: UserRole; password: string }) => {
    try {
      const payload: CreateUserPayload = {
        name: data.name.trim(),
        email: data.email.trim().toLowerCase(),
        password: data.password,
        role: data.role,
        is_active: true,
      };
      const created = await apiCreateUser(payload);
      const ui = toUiUser(created);
      if (ui) setUsers((prev) => [...prev, ui]);
      else await reload();
      return { ok: true };
    } catch (err) {
      return { ok: false, error: toErrorMessage(err, 'No se pudo crear el usuario.') };
    }
  }, [reload]);

  const updateUser = useCallback(async (id: string, data: { name: string; email: string; role: UserRole }) => {
    try {
      const payload: UpdateUserPayload = {
        name: data.name.trim(),
        email: data.email.trim().toLowerCase(),
        role: data.role,
      };
      const updated = await apiUpdateUser(id, payload);
      const ui = toUiUser(updated);
      if (ui) setUsers((prev) => prev.map((u) => (u.id === id ? ui : u)));
      else await reload();
      return { ok: true };
    } catch (err) {
      return { ok: false, error: toErrorMessage(err, 'No se pudo actualizar el usuario.') };
    }
  }, [reload]);

  const setActive = useCallback(async (id: string, active: boolean) => {
    try {
      const updated = await apiUpdateUser(id, { is_active: active });
      const ui = toUiUser(updated);
      if (ui) setUsers((prev) => prev.map((u) => (u.id === id ? ui : u)));
      else await reload();
      return { ok: true };
    } catch (err) {
      return { ok: false, error: toErrorMessage(err, 'No se pudo cambiar el estado.') };
    }
  }, [reload]);

  return {
    isLoading: loading,
    isAuthBlocked: authBlocked,
    isForbidden: forbidden,
    isConfigMissing: configMissing,
    errorMessage,
    retry,
    status: loading ? 'loading' : failed ? 'error' : users.length === 0 ? 'empty' : 'success',
    users,
    createUser,
    updateUser,
    setActive,
  };
}
