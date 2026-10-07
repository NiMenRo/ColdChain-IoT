import { Routes, Route, Navigate, Outlet, useLocation } from 'react-router';
import { motion, useReducedMotion } from 'motion/react';
import { ProtectedRoute } from './ProtectedRoute';
import { RoleGuard } from './RoleGuard';
import { ROUTE_PERMISSIONS } from '../config/rbac';
import { TopNav } from '../components/TopNav';
import { Sidebar } from '../components/Sidebar';
import { DashboardView }       from '../components/views/DashboardView';
import { DevicesView }         from '../components/views/DevicesView';
import { TrafficView }         from '../components/views/TrafficView';
import { AlertsView }          from '../components/views/AlertsView';
import { AnalyticsView }       from '../components/views/AnalyticsView';
import { SimulationView }      from '../components/views/SimulationView';
import { SettingsView }        from '../components/views/SettingsView';
import { UserManagementView }  from '../components/views/UserManagementView';
import { AuditView }           from '../components/views/AuditView';
import { LoginView }           from '../components/views/auth/LoginView';
import { ForbiddenView }       from '../components/views/auth/ForbiddenView';

function AppLayout() {
  const location = useLocation();
  const reduceMotion = useReducedMotion();
  return (
    <div className="d-flex min-vh-100" style={{ background: '#F5F8FA', fontFamily: "'Inter', sans-serif" }}>
      <a href="#main-content" className="visually-hidden-focusable position-fixed" style={{ left: 16, top: 16, zIndex: 999, background: '#fff', padding: 12, borderRadius: 8, color: '#123B5D' }}>
        Saltar al contenido
      </a>
      <Sidebar />
      <div className="flex-grow-1 overflow-hidden d-flex flex-column" style={{ minWidth: 0 }}>
        <TopNav />
        <motion.main
          key={location.pathname}
          initial={{ opacity: reduceMotion ? 1 : 0, y: reduceMotion ? 0 : 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.18 }}
          id="main-content"
          tabIndex={-1}
          className="flex-grow-1 overflow-auto"
          style={{ padding: '24px' }}
        >
          <Outlet />
        </motion.main>
      </div>
    </div>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginView />} />
      <Route path="/403"   element={<ForbiddenView />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/app" element={<AppLayout />}>
          <Route path="dashboard"  element={<DashboardView />} />
          <Route path="sensors"    element={<DevicesView />} />
          <Route path="traffic"    element={<TrafficView />} />
          <Route path="alerts"     element={<AlertsView />} />
          <Route path="qos"         element={<AnalyticsView />} />

          <Route path="simulation" element={
            <RoleGuard allowedRoles={ROUTE_PERMISSIONS['/app/simulation']}>
              <SimulationView />
            </RoleGuard>
          } />
          <Route path="settings" element={
            <RoleGuard allowedRoles={ROUTE_PERMISSIONS['/app/settings']}>
              <SettingsView />
            </RoleGuard>
          } />
          <Route path="users" element={
            <RoleGuard allowedRoles={ROUTE_PERMISSIONS['/app/users']}>
              <UserManagementView />
            </RoleGuard>
          } />
          <Route path="audit" element={
            <RoleGuard allowedRoles={ROUTE_PERMISSIONS['/app/audit']}>
              <AuditView />
            </RoleGuard>
          } />

          <Route index element={<Navigate to="dashboard" replace />} />
        </Route>
      </Route>

      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
