import { Navigate } from 'react-router';
import { ReactNode } from 'react';
import { useAuth } from '../hooks/useAuth';
import { UserRole } from '../config/rbac';

interface RoleGuardProps {
  allowedRoles: UserRole[];
  children: ReactNode;
}

export function RoleGuard({ allowedRoles, children }: RoleGuardProps) {
  const { role } = useAuth();

  if (!role || !allowedRoles.includes(role)) {
    return <Navigate to="/403" replace />;
  }

  return <>{children}</>;
}
