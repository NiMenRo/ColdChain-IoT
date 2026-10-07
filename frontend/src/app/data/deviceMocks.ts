import { Device, DeviceSensor, DeviceReadingSnapshot } from '../types/devices';

export const INITIAL_DEVICES: Device[] = [
  { id: 'd-001', code: 'CAVA-NTE', name: 'Cava Norte',      location: 'Zona A', device_type: 'cold_room',             status: 'active',      registration_date: '2026-09-01T08:00:00' },
  { id: 'd-002', code: 'VIT-ENT',  name: 'Vitrina Entrada', location: 'Zona B', device_type: 'refrigerated_showcase', status: 'active',      registration_date: '2026-09-01T08:05:00' },
  { id: 'd-003', code: 'CAVA-SUR', name: 'Cava Sur',        location: 'Zona A', device_type: 'cold_room',             status: 'error',       registration_date: '2026-09-02T09:00:00' },
  { id: 'd-004', code: 'VIT-SALA', name: 'Vitrina Sala',    location: 'Zona C', device_type: 'refrigerated_showcase', status: 'maintenance', registration_date: '2026-09-02T09:10:00' },
  { id: 'd-005', code: 'CAVA-CTR', name: 'Cava Central',    location: 'Zona B', device_type: 'cold_room',             status: 'active',      registration_date: '2026-09-03T10:00:00' },
  { id: 'd-006', code: 'VIT-BCK',  name: 'Vitrina Back',    location: 'Zona C', device_type: 'refrigerated_showcase', status: 'inactive',    registration_date: '2026-09-03T10:15:00' },
];

export const INITIAL_SENSORS: DeviceSensor[] = [
  { id: 's-001', device_id: 'd-001', sensor_type: 'temperature' },
  { id: 's-002', device_id: 'd-001', sensor_type: 'humidity' },
  { id: 's-003', device_id: 'd-001', sensor_type: 'energy' },
  { id: 's-004', device_id: 'd-002', sensor_type: 'temperature' },
  { id: 's-005', device_id: 'd-002', sensor_type: 'humidity' },
  { id: 's-006', device_id: 'd-002', sensor_type: 'energy' },
  { id: 's-007', device_id: 'd-003', sensor_type: 'temperature' },
  { id: 's-008', device_id: 'd-003', sensor_type: 'humidity' },
  { id: 's-009', device_id: 'd-003', sensor_type: 'energy' },
  { id: 's-010', device_id: 'd-004', sensor_type: 'temperature' },
  { id: 's-011', device_id: 'd-004', sensor_type: 'humidity' },
  { id: 's-012', device_id: 'd-004', sensor_type: 'energy' },
  { id: 's-013', device_id: 'd-005', sensor_type: 'temperature' },
  { id: 's-014', device_id: 'd-005', sensor_type: 'humidity' },
  { id: 's-015', device_id: 'd-005', sensor_type: 'energy' },
  { id: 's-016', device_id: 'd-006', sensor_type: 'temperature' },
  { id: 's-017', device_id: 'd-006', sensor_type: 'humidity' },
];

export const INITIAL_READINGS: DeviceReadingSnapshot[] = [
  { device_id: 'd-001', temperature: 2.1,  humidity: 86,   energy: 'on',  timestamp: '2026-10-04T10:41:00' },
  { device_id: 'd-002', temperature: 3.4,  humidity: 88,   energy: 'on',  timestamp: '2026-10-04T10:40:00' },
  { device_id: 'd-003', temperature: 6.8,  humidity: 92,   energy: 'on',  timestamp: '2026-10-04T10:38:00' },
  { device_id: 'd-004', temperature: null, humidity: null, energy: 'off', timestamp: '2026-10-04T09:15:00' },
  { device_id: 'd-005', temperature: 1.9,  humidity: 87,   energy: 'on',  timestamp: '2026-10-04T10:41:00' },
  { device_id: 'd-006', temperature: null, humidity: null, energy: 'off', timestamp: '2026-10-04T08:30:00' },
];

export const HISTORY_MOCK: Record<string, { ts: string; temperature: number | null; humidity: number | null; energy: 'on' | 'off' }[]> = {
  'd-001': [
    { ts: '10:41', temperature: 2.1, humidity: 86, energy: 'on' },
    { ts: '10:31', temperature: 2.3, humidity: 85, energy: 'on' },
    { ts: '10:21', temperature: 2.0, humidity: 87, energy: 'on' },
    { ts: '10:11', temperature: 1.9, humidity: 86, energy: 'on' },
    { ts: '10:01', temperature: 2.2, humidity: 85, energy: 'on' },
  ],
  'd-002': [
    { ts: '10:40', temperature: 3.4, humidity: 88, energy: 'on' },
    { ts: '10:30', temperature: 3.6, humidity: 89, energy: 'on' },
    { ts: '10:20', temperature: 3.8, humidity: 88, energy: 'on' },
    { ts: '10:10', temperature: 4.1, humidity: 90, energy: 'on' },
    { ts: '10:00', temperature: 3.9, humidity: 88, energy: 'on' },
  ],
  'd-003': [
    { ts: '10:38', temperature: 6.8, humidity: 92, energy: 'on' },
    { ts: '10:28', temperature: 6.2, humidity: 91, energy: 'on' },
    { ts: '10:18', temperature: 5.9, humidity: 90, energy: 'on' },
    { ts: '10:08', temperature: 5.4, humidity: 89, energy: 'on' },
    { ts: '09:58', temperature: 4.9, humidity: 88, energy: 'on' },
  ],
  'd-005': [
    { ts: '10:41', temperature: 1.9, humidity: 87, energy: 'on' },
    { ts: '10:31', temperature: 2.1, humidity: 87, energy: 'on' },
    { ts: '10:21', temperature: 2.0, humidity: 86, energy: 'on' },
    { ts: '10:11', temperature: 1.8, humidity: 87, energy: 'on' },
    { ts: '10:01', temperature: 1.9, humidity: 86, energy: 'on' },
  ],
};
