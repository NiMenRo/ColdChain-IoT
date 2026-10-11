export type AuditAction =
  | 'user.create'
  | 'user.update'
  | 'user.password_reset'
  | 'device.create'
  | 'device.sensors_update'
  | 'system_config.update'
  | 'alert.acknowledge'
  | 'notification.process'
  | 'notification.status';

export type AuditResult = 'success' | 'failure';

export interface AuditLog {
  id: string;
  timestamp: string;
  actor: string;
  action: AuditAction;
  resource: string;
  result: AuditResult;
  old_value: string | null;
  new_value: string | null;
}

/** Forma de listado que el backend real expone; el prototipo pagina en cliente. */
export interface AuditLogListResponse {
  total: number;
  page: number;
  per_page: number;
  count: number;
  results: AuditLog[];
}

export const AUDIT_ACTIONS: AuditAction[] = [
  'user.create',
  'user.update',
  'user.password_reset',
  'device.create',
  'device.sensors_update',
  'system_config.update',
  'alert.acknowledge',
  'notification.process',
  'notification.status',
];
