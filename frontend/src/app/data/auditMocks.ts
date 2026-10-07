import { AuditLog } from '../types/audit';

function json(value: unknown): string {
  return JSON.stringify(value);
}

export const MOCK_AUDIT_LOGS: AuditLog[] = [
  {
    id: 'A021', timestamp: '2026-10-05T11:20:00', actor: 'admin@coldchain.iot',
    action: 'device.sensors_update', resource: 'devices/d-006', result: 'success',
    old_value: json({ sensors: ['temperature', 'humidity'] }),
    new_value: json({ sensors: ['temperature', 'humidity', 'energy'] }),
  },
  {
    id: 'A020', timestamp: '2026-10-05T11:05:00', actor: 'admin@coldchain.iot',
    action: 'device.create', resource: 'devices/d-006', result: 'success',
    old_value: null,
    new_value: json({ code: 'VIT-BCK', name: 'Vitrina Back', device_type: 'refrigerated_showcase', location: 'Zona C', status: 'inactive' }),
  },
  {
    id: 'A019', timestamp: '2026-10-05T10:48:00', actor: 'operador@coldchain.iot',
    action: 'alert.acknowledge', resource: 'alerts/ALT-001', result: 'success',
    old_value: json({ acknowledged: false }),
    new_value: json({ acknowledged: true }),
  },
  {
    id: 'A018', timestamp: '2026-10-05T10:40:12', actor: 'system@coldchain.iot',
    action: 'notification.process', resource: 'notifications/NOT-001', result: 'success',
    old_value: json({ status: 'pending' }),
    new_value: json({ status: 'sent', channel: 'email' }),
  },
  {
    id: 'A017', timestamp: '2026-10-05T10:40:18', actor: 'system@coldchain.iot',
    action: 'notification.status', resource: 'notifications/NOT-003', result: 'failure',
    old_value: json({ status: 'pending', channel: 'sms' }),
    new_value: json({ status: 'failed', channel: 'sms' }),
  },
  {
    id: 'A016', timestamp: '2026-10-05T09:12:00', actor: 'admin@coldchain.iot',
    action: 'system_config.update', resource: 'system_config', result: 'success',
    old_value: json({ temperature_max: 5, humidity_max: 92 }),
    new_value: json({ temperature_max: 4, humidity_max: 90 }),
  },
  {
    id: 'A015', timestamp: '2026-10-04T16:22:00', actor: 'admin@coldchain.iot',
    action: 'device.sensors_update', resource: 'devices/d-001', result: 'success',
    old_value: json({ sensors: ['temperature', 'humidity'] }),
    new_value: json({ sensors: ['temperature', 'humidity', 'energy'] }),
  },
  {
    id: 'A014', timestamp: '2026-10-04T15:01:00', actor: 'supervisor@coldchain.iot',
    action: 'alert.acknowledge', resource: 'alerts/ALT-004', result: 'success',
    old_value: json({ acknowledged: false }),
    new_value: json({ acknowledged: true }),
  },
  {
    id: 'A013', timestamp: '2026-10-04T14:10:00', actor: 'operador@coldchain.iot',
    action: 'alert.acknowledge', resource: 'alerts/ALT-007', result: 'failure',
    old_value: json({ acknowledged: false }),
    new_value: null,
  },
  {
    id: 'A012', timestamp: '2026-10-04T11:55:00', actor: 'admin@coldchain.iot',
    action: 'device.create', resource: 'devices/d-005', result: 'success',
    old_value: null,
    new_value: json({ code: 'CAVA-CTR', name: 'Cava Central', device_type: 'cold_room', location: 'Zona B', status: 'active' }),
  },
  {
    id: 'A011', timestamp: '2026-10-04T10:42:00', actor: 'admin@coldchain.iot',
    action: 'user.update', resource: 'users/8f3a2c1b', result: 'success',
    old_value: json({ name: 'Ana G.', role: 'admin', active: true }),
    new_value: json({ name: 'Ana García', role: 'admin', active: true }),
  },
  {
    id: 'A010', timestamp: '2026-10-04T10:15:33', actor: 'admin@coldchain.iot',
    action: 'user.create', resource: 'users/9d4e7f0a', result: 'success',
    old_value: null,
    new_value: json({ email: 'operador2@coldchain.iot', role: 'operador', active: true }),
  },
  {
    id: 'A009', timestamp: '2026-10-04T09:58:21', actor: 'admin@coldchain.iot',
    action: 'user.update', resource: 'users/3b2c9a1d', result: 'success',
    old_value: json({ role: 'operador', active: true }),
    new_value: json({ role: 'supervisor', active: true }),
  },
  {
    id: 'A008', timestamp: '2026-10-04T09:33:14', actor: 'admin@coldchain.iot',
    action: 'user.password_reset', resource: 'users/3b2c9a1d', result: 'success',
    old_value: null,
    new_value: json({ password_reset: true }),
  },
  {
    id: 'A007', timestamp: '2026-10-04T09:10:05', actor: 'admin@coldchain.iot',
    action: 'user.update', resource: 'users/8f3a2c1b', result: 'success',
    old_value: json({ active: false }),
    new_value: json({ active: true }),
  },
  {
    id: 'A006', timestamp: '2026-10-04T08:47:30', actor: 'supervisor@coldchain.iot',
    action: 'user.update', resource: 'users/2e5f8c3a', result: 'failure',
    old_value: json({ role: 'operador' }),
    new_value: json({ role: 'admin' }),
  },
  {
    id: 'A005', timestamp: '2026-10-03T16:22:55', actor: 'admin@coldchain.iot',
    action: 'user.create', resource: 'users/7c1a4b9e', result: 'success',
    old_value: null,
    new_value: json({ email: 'auditor2@coldchain.iot', role: 'auditor' }),
  },
  {
    id: 'A004', timestamp: '2026-10-03T15:04:18', actor: 'system@coldchain.iot',
    action: 'notification.process', resource: 'notifications/NOT-006', result: 'success',
    old_value: json({ status: 'pending' }),
    new_value: json({ status: 'sent', channel: 'dashboard' }),
  },
  {
    id: 'A003', timestamp: '2026-10-03T14:38:44', actor: 'admin@coldchain.iot',
    action: 'user.password_reset', resource: 'users/9d4e7f0a', result: 'success',
    old_value: null,
    new_value: json({ password_reset: true }),
  },
  {
    id: 'A002', timestamp: '2026-10-03T11:55:02', actor: 'admin@coldchain.iot',
    action: 'system_config.update', resource: 'system_config', result: 'failure',
    old_value: json({ energy_expected: 'on' }),
    new_value: json({ energy_expected: 'off' }),
  },
  {
    id: 'A001', timestamp: '2026-10-03T10:30:11', actor: 'admin@coldchain.iot',
    action: 'device.create', resource: 'devices/d-001', result: 'success',
    old_value: null,
    new_value: json({ code: 'CAVA-NTE', name: 'Cava Norte', device_type: 'cold_room', location: 'Zona A', status: 'active' }),
  },
];
