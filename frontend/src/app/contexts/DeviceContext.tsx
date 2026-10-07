import { createContext, useContext, useState, ReactNode } from 'react';
import {
  Device,
  DeviceFormData,
  DeviceReadingSnapshot,
  DeviceSensor,
  SensorType,
  DEVICE_TYPE_LABEL,
  SENSOR_LABEL,
  ALL_SENSORS,
} from '../types/devices';
import { INITIAL_DEVICES, INITIAL_READINGS, INITIAL_SENSORS } from '../data/deviceMocks';

export type { Device, DeviceFormData, DeviceSensor, SensorType, DeviceReadingSnapshot };
export { DEVICE_TYPE_LABEL, SENSOR_LABEL, ALL_SENSORS };
export type { DeviceType, DeviceStatus } from '../types/devices';

let _nextDevice = 7;
let _nextSensor = 18;

function nextDeviceId() { return `d-${String(_nextDevice++).padStart(3, '0')}`; }
function nextSensorId() { return `s-${String(_nextSensor++).padStart(3, '0')}`; }

interface DeviceContextValue {
  devices: Device[];
  sensors: DeviceSensor[];
  readings: DeviceReadingSnapshot[];
  getSensors: (deviceId: string) => SensorType[];
  getReading: (deviceId: string) => DeviceReadingSnapshot | undefined;
  addDevice: (data: DeviceFormData) => { ok: boolean; error?: string };
  replaceSensors: (deviceId: string, sensorTypes: SensorType[]) => { ok: boolean; error?: string };
}

const DeviceContext = createContext<DeviceContextValue | null>(null);

export function DeviceProvider({ children }: { children: ReactNode }) {
  const [devices, setDevices] = useState<Device[]>(INITIAL_DEVICES);
  const [sensors, setSensors] = useState<DeviceSensor[]>(INITIAL_SENSORS);
  const [readings] = useState<DeviceReadingSnapshot[]>(INITIAL_READINGS);

  function getSensors(deviceId: string): SensorType[] {
    return sensors.filter(s => s.device_id === deviceId).map(s => s.sensor_type);
  }

  function getReading(deviceId: string) {
    return readings.find(r => r.device_id === deviceId);
  }

  function addDevice(data: DeviceFormData) {
    if (data.sensors.length === 0) {
      return { ok: false, error: 'El dispositivo debe tener al menos un sensor configurado.' };
    }
    const code = data.code.trim().toUpperCase();
    if (devices.some(d => d.code.toUpperCase() === code)) {
      return { ok: false, error: 'Ya existe un dispositivo con ese código.' };
    }
    const id = nextDeviceId();
    const now = new Date().toISOString();
    setDevices(prev => [...prev, {
      id,
      code,
      name: data.name.trim(),
      location: data.location.trim(),
      device_type: data.device_type,
      status: data.status,
      registration_date: now,
    }]);
    setSensors(prev => [
      ...prev,
      ...data.sensors.map(sensor_type => ({
        id: nextSensorId(),
        device_id: id,
        sensor_type,
      })),
    ]);
    return { ok: true };
  }

  /** Equivale semánticamente a PUT /devices/{id}/sensors: reemplaza el conjunto completo. */
  function replaceSensors(deviceId: string, sensorTypes: SensorType[]) {
    if (sensorTypes.length === 0) {
      return { ok: false, error: 'El dispositivo debe tener al menos un sensor configurado.' };
    }
    const unique = Array.from(new Set(sensorTypes));
    setSensors(prev => [
      ...prev.filter(s => s.device_id !== deviceId),
      ...unique.map(sensor_type => ({
        id: nextSensorId(),
        device_id: deviceId,
        sensor_type,
      })),
    ]);
    return { ok: true };
  }

  return (
    <DeviceContext.Provider value={{ devices, sensors, readings, getSensors, getReading, addDevice, replaceSensors }}>
      {children}
    </DeviceContext.Provider>
  );
}

export function useDevices(): DeviceContextValue {
  const ctx = useContext(DeviceContext);
  if (!ctx) throw new Error('useDevices must be used inside <DeviceProvider>');
  return ctx;
}
