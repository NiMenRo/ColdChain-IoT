export type UserRole = 'admin' | 'supervisor' | 'operador' | 'auditor';

// â”€â”€â”€ Route-level permissions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export const ROUTE_PERMISSIONS: Record<string, UserRole[]> = {
  '/app/dashboard':   ['admin', 'supervisor', 'operador', 'auditor'],
  '/app/sensors':     ['admin', 'supervisor', 'operador', 'auditor'],
  '/app/traffic':     ['admin', 'supervisor', 'operador', 'auditor'],
  '/app/alerts':      ['admin', 'supervisor', 'operador', 'auditor'],
  '/app/qos':         ['admin', 'supervisor', 'operador', 'auditor'],
  '/app/simulation':  ['admin', 'supervisor'],
  '/app/settings':    ['admin'],
  '/app/users':       ['admin'],
  '/app/audit':       ['admin', 'auditor'],
};

// â”€â”€â”€ Action-level permissions (single source of truth) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export const ACTION_PERMISSIONS = {
  updateDevices:      ['admin']                                  as UserRole[],
  manageDevices:      ['admin']                                  as UserRole[],
  acknowledgeAlert:   ['admin', 'supervisor', 'operador']        as UserRole[],
  runSimulation:      ['admin', 'supervisor']                    as UserRole[],
  selectScenario:     ['admin', 'supervisor']                    as UserRole[],
  manageSettings:     ['admin']                                  as UserRole[],
  manageUsers:        ['admin']                                  as UserRole[],
  exportData:         ['admin', 'supervisor', 'auditor']         as UserRole[],
  viewAuditLogs:      ['admin', 'auditor']                       as UserRole[],
} as const;

export type ActionPermission = keyof typeof ACTION_PERMISSIONS;

// â”€â”€â”€ Sidebar menu visibility â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export const SIDEBAR_ROLES: Record<string, UserRole[]> = {
  dashboard:    ['admin', 'supervisor', 'operador', 'auditor'],
  sensors:      ['admin', 'supervisor', 'operador', 'auditor'],
  traffic:      ['admin', 'supervisor', 'operador', 'auditor'],
  alerts:       ['admin', 'supervisor', 'operador', 'auditor'],
  qos:          ['admin', 'supervisor', 'operador', 'auditor'],
  simulation:   ['admin', 'supervisor'],
  settings:     ['admin'],
  users:        ['admin'],
  audit:        ['admin', 'auditor'],
};

// â”€â”€â”€ Role display labels â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export const ROLE_LABELS: Record<UserRole, string> = {
  admin:      'Administrador',
  supervisor: 'Supervisor',
  operador:   'Operador',
  auditor:    'Auditor',
};

// â”€â”€â”€ Helper functions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export function hasRoutePermission(role: UserRole, path: string): boolean {
  const allowed = ROUTE_PERMISSIONS[path];
  return !!allowed && allowed.includes(role);
}

export function hasActionPermission(role: UserRole | null, action: ActionPermission): boolean {
  if (!role) return false;
  return ACTION_PERMISSIONS[action].includes(role);
}
