import type { DeviceLatestValues } from '../../services/api/history';
import type { DeviceLatestSnapshot } from '../types/devices';

/** Cada sensor conserva la fecha de su propia fila; no se inventa un bundle. */
export function deviceLatestSnapshot(values: DeviceLatestValues): DeviceLatestSnapshot | undefined {
  const timestamps = Object.values(values).flatMap(row => row ? [row.timestamp] : []);
  if (timestamps.length === 0) return undefined;
  return {
    temperature: values.temperature?.temperature ?? null,
    humidity: values.humidity?.humidity ?? null,
    energy: values.energy?.energy ?? null,
    timestamp: timestamps.sort((a, b) => Date.parse(b) - Date.parse(a))[0],
    sensor_timestamps: {
      temperature: values.temperature?.timestamp ?? null,
      humidity: values.humidity?.timestamp ?? null,
      energy: values.energy?.timestamp ?? null,
    },
  };
}
