import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from 'react';
import {
  Device,
  DeviceFormData,
  DeviceReadingSnapshot,
  SensorType,
  DEVICE_TYPE_LABEL,
  SENSOR_LABEL,
  ALL_SENSORS,
} from '../types/devices';
import { ApiError } from '../../services/api/client';
import {
  apiCreateDevice,
  apiGetDeviceDetail,
  apiGetDevices,
  apiReplaceDeviceSensors,
  toCreateDevicePayload,
} from '../../services/api/devices';
import {
  apiGetDeviceHistory,
  apiGetReadingTrends,
  type HistoryReading,
  type ReadingTrendPoint,
} from '../../services/api/history';

export type { Device, DeviceFormData, SensorType, DeviceReadingSnapshot };
export { DEVICE_TYPE_LABEL, SENSOR_LABEL, ALL_SENSORS };
export type { DeviceType, DeviceStatus } from '../types/devices';

export type DeviceSectionStatus = 'loading' | 'success' | 'empty' | 'error';

function toSnapshot(deviceId: string, r: HistoryReading): DeviceReadingSnapshot {
  return {
    id: r.id,
    device_id: deviceId,
    temperature: r.temperature,
    humidity: r.humidity,
    energy: r.energy,
    timestamp: r.timestamp,
  };
}

function toErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return 'Ya existe un dispositivo con ese código.';
    if (err.status === 403) return 'Sin permiso: esta operación requiere rol administrador.';
    if (err.status === 400) return 'Datos inválidos: revise el formulario e intente de nuevo.';
    return err.message;
  }
  return fallback;
}

interface DeviceContextValue {
  devices: Device[];
  devicesStatus: DeviceSectionStatus;
  readingsStatus: DeviceSectionStatus;
  /** Sin autenticación real (login mock) la API responde 401: se documenta, no se inventa token. */
  isAuthBlocked: boolean;
  isConfigMissing: boolean;
  errorMessage: string | null;
  retry: () => void;
  getSensors: (deviceId: string) => SensorType[];
  getReading: (deviceId: string) => DeviceReadingSnapshot | undefined;
  getHistory: (deviceId: string) => DeviceReadingSnapshot[];
  getTrends: (deviceId: string) => ReadingTrendPoint[];
  fetchTrends: (deviceId: string) => Promise<void>;
  addDevice: (data: DeviceFormData) => Promise<{ ok: boolean; error?: string }>;
  replaceSensors: (deviceId: string, sensorTypes: SensorType[]) => Promise<{ ok: boolean; error?: string }>;
}

const DeviceContext = createContext<DeviceContextValue | null>(null);

/** Últimas lecturas por dispositivo (máx. 5, ordenadas por el backend). */
const HISTORY_PER_DEVICE = 5;

export function DeviceProvider({ children }: { children: ReactNode }) {
  const [devices, setDevices] = useState<Device[]>([]);
  const [sensorsByDevice, setSensorsByDevice] = useState<Record<string, SensorType[]>>({});
  const [historyByDevice, setHistoryByDevice] = useState<Record<string, DeviceReadingSnapshot[]>>({});
  const [trendsByDevice, setTrendsByDevice] = useState<Record<string, ReadingTrendPoint[]>>({});
  const [devicesStatus, setDevicesStatus] = useState<DeviceSectionStatus>('loading');
  const [readingsStatus, setReadingsStatus] = useState<DeviceSectionStatus>('loading');
  const [isAuthBlocked, setIsAuthBlocked] = useState(false);
  const [isConfigMissing, setIsConfigMissing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setDevicesStatus('loading');
    setReadingsStatus('loading');

    (async () => {
      let list: Device[];
      try {
        const res = await apiGetDevices({ page: 1, per_page: 100 });
        list = res.results;
      } catch (err) {
        if (cancelled) return;
        const apiErr = err instanceof ApiError ? err : null;
        setDevices([]);
        setSensorsByDevice({});
        setHistoryByDevice({});
        setDevicesStatus('error');
        setReadingsStatus('error');
        setIsAuthBlocked(apiErr?.isAuthError ?? false);
        setIsConfigMissing(apiErr?.code === 'NO_BASE_URL');
        setErrorMessage(err instanceof Error ? err.message : 'No se pudieron cargar los dispositivos.');
        return;
      }
      if (cancelled) return;
      setDevices(list);
      setDevicesStatus(list.length === 0 ? 'empty' : 'success');
      setIsAuthBlocked(false);
      setIsConfigMissing(false);
      setErrorMessage(null);

      // Detalle (sensores) + historial (lecturas) por dispositivo, en paralelo.
      // GET /devices/{id} y GET /history/devices/{code}/history existen en el backend.
      const settled = await Promise.allSettled(
        list.map(async (d) => {
          const [detail, history] = await Promise.all([
            apiGetDeviceDetail(d.id),
            apiGetDeviceHistory(d.code, { page: 1, per_page: HISTORY_PER_DEVICE }),
          ]);
          return { device: d, sensors: detail.sensors, readings: history.results.map((r) => toSnapshot(d.id, r)) };
        }),
      );
      if (cancelled) return;
      const sensors: Record<string, SensorType[]> = {};
      const history: Record<string, DeviceReadingSnapshot[]> = {};
      let anyOk = false;
      let sawAuth = false;
      for (const r of settled) {
        if (r.status === 'fulfilled') {
          anyOk = true;
          sensors[r.value.device.id] = r.value.sensors;
          history[r.value.device.id] = r.value.readings;
        } else if (r.reason instanceof ApiError && r.reason.isAuthError) {
          sawAuth = true;
        }
      }
      setSensorsByDevice(sensors);
      setHistoryByDevice(history);
      if (!anyOk && list.length > 0) {
        setReadingsStatus('error');
        setIsAuthBlocked(sawAuth);
        setErrorMessage(sawAuth
          ? 'La API requiere autenticación Bearer. Inicie sesión nuevamente si su sesión expiró.'
          : 'No se pudieron cargar las lecturas de los dispositivos.');
      } else {
        setReadingsStatus('success');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [attempt]);

  function getSensors(deviceId: string): SensorType[] {
    return sensorsByDevice[deviceId] ?? [];
  }

  function getHistory(deviceId: string): DeviceReadingSnapshot[] {
    return historyByDevice[deviceId] ?? [];
  }

  function getReading(deviceId: string) {
    // results ya vienen ordenados por timestamp desc desde el backend.
    return getHistory(deviceId)[0];
  }

  function getTrends(deviceId: string): ReadingTrendPoint[] {
    return trendsByDevice[deviceId] ?? [];
  }

  /** Carga perezosa de tendencias agregadas por el backend (tira prom/min/máx). */
  async function fetchTrends(deviceId: string): Promise<void> {
    const device = devices.find((d) => d.id === deviceId);
    if (!device || trendsByDevice[deviceId]) return;
    const points = await apiGetReadingTrends('hour', { device_code: device.code });
    setTrendsByDevice((prev) => ({ ...prev, [deviceId]: points }));
  }

  async function addDevice(data: DeviceFormData) {
    if (data.sensors.length === 0) {
      return { ok: false, error: 'El dispositivo debe tener al menos un sensor configurado.' };
    }
    const code = data.code.trim().toUpperCase();
    if (devices.some((d) => d.code.toUpperCase() === code)) {
      return { ok: false, error: 'Ya existe un dispositivo con ese código.' };
    }
    try {
      const created = await apiCreateDevice(toCreateDevicePayload(data));
      setDevices((prev) => [...prev, created.device]);
      setSensorsByDevice((prev) => ({ ...prev, [created.device.id]: created.sensors }));
      return { ok: true };
    } catch (err) {
      return { ok: false, error: toErrorMessage(err, 'No se pudo crear el dispositivo.') };
    }
  }

  /** Equivale a PUT /devices/{id}/sensors: reemplaza el conjunto completo (solo admin). */
  async function replaceSensors(deviceId: string, sensorTypes: SensorType[]) {
    if (sensorTypes.length === 0) {
      return { ok: false, error: 'El dispositivo debe tener al menos un sensor configurado.' };
    }
    try {
      const updated = await apiReplaceDeviceSensors(deviceId, Array.from(new Set(sensorTypes)));
      setSensorsByDevice((prev) => ({ ...prev, [deviceId]: updated.sensors }));
      return { ok: true };
    } catch (err) {
      return { ok: false, error: toErrorMessage(err, 'No se pudo actualizar la configuración de sensores.') };
    }
  }

  return (
    <DeviceContext.Provider
      value={{
        devices,
        devicesStatus,
        readingsStatus,
        isAuthBlocked,
        isConfigMissing,
        errorMessage,
        retry,
        getSensors,
        getReading,
        getHistory,
        getTrends,
        fetchTrends,
        addDevice,
        replaceSensors,
      }}
    >
      {children}
    </DeviceContext.Provider>
  );
}

export function useDevices(): DeviceContextValue {
  const ctx = useContext(DeviceContext);
  if (!ctx) throw new Error('useDevices must be used inside <DeviceProvider>');
  return ctx;
}
