import { createContext, useState, useEffect, ReactNode } from 'react';
import {
  login as serviceLogin,
  logout as serviceLogout,
  getCurrentUser,
  validateSession,
  User,
} from '../../services/authService';
import { UserRole } from '../config/rbac';

interface AuthContextValue {
  user: User | null;
  role: UserRole | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Pintado inicial con sesión guardada + validación real contra GET /auth/me.
  // Token ausente/inválido/expirado (401) → sesión limpia → /login vía ProtectedRoute.
  useEffect(() => {
    let cancelled = false;
    setUser(getCurrentUser());
    validateSession().then((valid) => {
      if (!cancelled) {
        setUser(valid);
        setIsLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = async (email: string, password: string) => {
    const result = await serviceLogin(email, password);
    if (result.success && result.user) {
      setUser(result.user);
    }
    return { success: result.success, error: result.error };
  };

  const logout = async () => {
    await serviceLogout();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        role: user?.role ?? null,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
