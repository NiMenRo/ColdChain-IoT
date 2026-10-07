import { Navigate, Outlet, useLocation } from 'react-router';
import { useAuth } from '../hooks/useAuth';
import { LoaderCircle } from 'lucide-react';

export function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div role="status" className="flex min-h-screen items-center justify-center gap-3 bg-background text-sm text-muted-foreground">
        <LoaderCircle size={18} className="animate-spin" />
        Cargando sesión...
      </div>
    );
  }

  if (!isAuthenticated) {
    // Preserve the intended destination so LoginView can redirect back after login
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
}
