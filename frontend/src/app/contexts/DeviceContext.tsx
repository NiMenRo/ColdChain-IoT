import { createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode } from 'react';
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
  runBulkCreate,
  type BulkCreateSummary,
} from '../../services/api/bulkDevices';
import {
  apiGetDeviceHistory,
  apiGetReadingTrends,
  type HistoryReading,
  type ReadingTrendPoint,
} from '../../services/api/history';
import { usePolling, DEVICES_POLL_MS } from '../hooks/usePolling';

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
  /** Refresco en segundo plano en curso (los datos visibles se conservan). */
  isRefreshing: boolean;
  /** Sello local de la última actualización exitosa (null = ninguna aún). */
  lastUpdated: string | null;
  /** Error solo del último refresco en segundo plano (no borra datos). */
  refreshError: string | null;
  /** Sin autenticación real (login mock) la API responde 401: se documenta, no se inventa token. */
  isAuthBlocked: boolean;
  isConfigMissing: boolean;
  errorMessage: string | null;
  retry: () => void;
  /** Actualización manual inmediata (recarga completa). */
  refresh: () => void;
  getSensors: (deviceId: string) => SensorType[];
  getReading: (deviceId: string) => DeviceReadingSnapshot | undefined;
  getHistory: (deviceId: string) => DeviceReadingSnapshot[];
  getTrends: (deviceId: string) => ReadingTrendPoint[];
  fetchTrends: (deviceId: string) => Promise<void>;
  addDevice: (data: DeviceFormData) => Promise<{ ok: boolean; error?: string }>;
  replaceSensors: (deviceId: string, sensorTypes: SensorType[]) => Promise<{ ok: boolean; error?: string }>;
  /**
   * Creación masiva (fase D): reutiliza POST /devices por dispositivo con
   * concurrencia acotada. Integra los creados al estado en UNA sola
   * actualización (sin duplicados aunque el polling intercale).
   */
  addManyDevices: (
    items: DeviceFormData[],
    opts?: {
      concurrency?: number;
      onProgress?: (done: number, total: number) => void;
      isCancelled?: () => boolean;
    },
  ) => Promise<BulkCreateSummary>;
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
  const [pollSeq, setPollSeq] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const busyRef = useRef(false);
  const backgroundRef = useRef(false);
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  const refresh = useCallback(() => {
    backgroundRef.current = false;
    setAttempt((n) => n + 1);
  }, []);

  // Polling ligero en segundo plano (10 s): lista + últimas lecturas.
  // Sensores/detalle no se repiten (solo cambian vía addDevice/replaceSensors,
  // que ya actualizan el estado local). Pausado con pestaña oculta.
  usePolling(true, DEVICES_POLL_MS, useCallback(() => {
    backgroundRef.current = true;
    setPollSeq((n) => n + 1);
  }, []), busyRef);

  useEffect(() => {
    let cancelled = false;
    const background = backgroundRef.current;
    backgroundRef.current = false;
    if (background) {
      setRefreshing(true);
    } else {
      setDevicesStatus('loading');
      setReadingsStatus('loading');
    }
    busyRef.current = true;

    (async () => {
      let list: Device[];
      try {
        const res = await apiGetDevices({ page: 1, per_page: 100 });
        list = res.results;
      } catch (err) {
        if (cancelled || !mountedRef.current) return;
        busyRef.current = false;
        if (background) {
          // Se conservan los últimos datos; aviso discreto sin borrar nada.
          setRefreshError(err instanceof Error ? err.message : 'No se pudo actualizar.');
          setRefreshing(false);
          return;
        }
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
      if (cancelled || !mountedRef.current) return;
      busyRef.current = false;
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
        if (background) {
          setRefreshError('No se pudieron actualizar las lecturas.');
        } else {
          setReadingsStatus('error');
          setIsAuthBlocked(sawAuth);
          setErrorMessage(sawAuth
            ? 'La API requiere autenticación Bearer. Inicie sesión nuevamente si su sesión expiró.'
            : 'No se pudieron cargar las lecturas de los dispositivos.');
        }
      } else {
        setReadingsStatus('success');
        setRefreshError(null);
        setLastUpdated(new Date().toLocaleTimeString('es-CO', { hour12: false }));
      }
      if (background) setRefreshing(false);
    })();

    return () => {
      cancelled = true;
      busyRef.current = false;
    };
  }, [attempt, pollSeq]);

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
    // El código lo genera siempre el backend (CAVA-*/VITRINA-*): sin chequeo local.
    try {
      const created = await apiCreateDevice(toCreateDevicePayload(data));
      setDevices((prev) => [...prev, created.device]);
      setSensorsByDevice((prev) => ({ ...prev, [created.device.id]: created.sensors }));
      return { ok: true };
    } catch (err) {
      return { ok: false, error: toErrorMessage(err, 'No se pudo crear el dispositivo.') };
    }
  }

  async function addManyDevices(
    items: DeviceFormData[],
    opts?: {
      concurrency?: number;
      onProgress?: (done: number, total: number) => void;
      isCancelled?: () => boolean;
    },
  ): Promise<BulkCreateSummary> {
    if (items.length === 0) {
      return { requested: 0, created: 0, failed: [], cancelled: false };
    }
    const { summary, details } = await runBulkCreate(items, opts);
    if (details.length > 0 && mountedRef.current) {
      // Inserción única y sin duplicados (el polling de 10 s puede haber
      // traído parte del lote entre tanto: se filtra por id).
      setDevices((prev) => {
        const known = new Set(prev.map((d) => d.id));
        const fresh = details.map((c) => c.device).filter((d) => !known.has(d.id));
        return fresh.length > 0 ? [...prev, ...fresh] : prev;
      });
      setSensorsByDevice((prev) => {
        const next = { ...prev };
        for (const c of details) next[c.device.id] = c.sensors;
        return next;
      });
    }
    return summary;
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
        isRefreshing: refreshing,
        lastUpdated,
        refreshError,
        isAuthBlocked,
        isConfigMissing,
        errorMessage,
        retry,
        refresh,
        getSensors,
        getReading,
        getHistory,
        getTrends,
        fetchTrends,
        addDevice,
        addManyDevices,
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
