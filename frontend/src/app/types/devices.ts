export type DeviceType = 'cold_room' | 'refrigerated_showcase';
export type DeviceStatus = 'active' | 'inactive' | 'maintenance' | 'error';
export type SensorType = 'temperature' | 'humidity' | 'energy';

export interface Device {
  id: string;
  code: string;
  name: string;
  location: string;
  device_type: DeviceType;
  status: DeviceStatus;
  registration_date: string;
}

export interface DeviceSensor {
  id: string;
  device_id: string;
  sensor_type: SensorType;
}

export interface DeviceFormData {
  code: string;
  name: string;
  location: string;
  device_type: DeviceType;
  status: DeviceStatus;
  sensors: SensorType[];
}

export const DEVICE_TYPE_LABEL: Record<DeviceType, string> = {
  cold_room:             'Cava',
  refrigerated_showcase: 'Vitrina',
};

export const SENSOR_LABEL: Record<SensorType, string> = {
  temperature: 'Temperatura',
  humidity:    'Humedad',
  energy:      'Energía',
};

export const ALL_SENSORS: SensorType[] = ['temperature', 'humidity', 'energy'];

/**
 * Lectura de un dispositivo tal como la expone el backend
 * (SensorReadingORM vía /history/readings o /history/devices/{code}/history).
 * `energy` es 'on' | 'off' | null (NULL = sensor no habilitado); nunca se
 * deriva de `device.status`.
 */
export interface DeviceReadingSnapshot {
  id: string;
  device_id: string;
  temperature: number | null;
  humidity: number | null;
  energy: 'on' | 'off' | null;
  timestamp: string;
}
