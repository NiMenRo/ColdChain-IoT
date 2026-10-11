// Creación masiva de dispositivos para el entorno de simulación (fase D).
//
// - Reutiliza EXCLUSIVAMENTE el flujo individual existente: POST /devices vía
//   apiCreateDevice/toCreateDevicePayload (mismas validaciones, mismos
//   permisos, misma generación de códigos CAVA-*/VITRINA-* en el backend).
//   No existe endpoint masivo: la evidencia de necesitarlo se evaluará con
//   esta funcionalidad en uso.
// - Crear dispositivos NO genera telemetría: solo registra los equipos; las
//   lecturas siguen dependiendo del simulador / adquisición existente.
// - Límite MAX_BULK_DEVICES = 100 por operación; concurrencia acotada
//   (defecto 4, máximo 8) para no saturar el backend.
// - Cancelación cooperativa y segura: nunca se aborta una petición en vuelo
//   (el servidor podría haberla creado igual); solo se dejan de emitir
//   nuevas y se espera a las pendientes. Lo no emitido queda como
//   "cancelado", nunca como fallo ambiguo.

import type {
  DeviceFormData,
  DeviceStatus,
  DeviceType,
} from '../../app/types/devices';
import { ALL_SENSORS, DEVICE_TYPE_LABEL } from '../../app/types/devices';
import { ApiError } from './client';
import {
  apiCreateDevice,
  toCreateDevicePayload,
  type DeviceDetailResponse,
} from './devices';

export const MAX_BULK_DEVICES = 100;
export const BULK_CONCURRENCY = 4;
export const BULK_MAX_CONCURRENCY = 8;

/** Cava, vitrina, o mezcla alternada (cava, vitrina, cava, …). */
export type BulkDeviceKind = DeviceType | 'mixed';

export interface BulkPlanInput {
  kind: BulkDeviceKind;
  count: number;
  /** Prefijo de nombres (se completa con tipo y número). */
  namePrefix: string;
  /** Ubicación base común (el backend no exige unicidad). */
  baseLocation: string;
  status: DeviceStatus;
}

/** Plan determinista y reproducible: nombres únicos dentro del lote. */
export function buildBulkPlan(input: BulkPlanInput): DeviceFormData[] {
  const count = Math.floor(Number(input.count));
  if (!Number.isFinite(count) || count < 1 || count > MAX_BULK_DEVICES) {
    throw new Error(`La cantidad debe ser un entero entre 1 y ${MAX_BULK_DEVICES}.`);
  }
  const prefix = (input.namePrefix ?? '').trim();
  if (!prefix) throw new Error('El prefijo de nombres es requerido.');
  const location = (input.baseLocation ?? '').trim();
  if (!location) throw new Error('La ubicación base es requerida.');

  const pad = String(count).length;
  const items: DeviceFormData[] = [];
  for (let i = 1; i <= count; i += 1) {
    const device_type: DeviceType =
      input.kind === 'mixed'
        ? (i % 2 === 1 ? 'cold_room' : 'refrigerated_showcase')
        : input.kind;
    items.push({
      name: `${prefix} ${DEVICE_TYPE_LABEL[device_type]} ${String(i).padStart(pad, '0')}`,
      location,
      device_type,
      status: input.status,
      sensors: [...ALL_SENSORS],
    });
  }
  return items;
}

export interface BulkItemFailure {
  index: number;
  name: string;
  error: string;
}

export interface BulkCreateSummary {
  requested: number;
  created: number;
  failed: BulkItemFailure[];
  /** true si el usuario canceló antes de emitir todo el lote. */
  cancelled: boolean;
}

export interface BulkRunOptions {
  concurrency?: number;
  /** (terminados, total) tras cada dispositivo resuelto. */
  onProgress?: (done: number, total: number) => void;
  /** La cancelación solo detiene la emisión de nuevas peticiones. */
  isCancelled?: () => boolean;
}

/** Mensajes de error coherentes con la creación individual. */
export function deviceErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return 'Ya existe un dispositivo con ese código.';
    if (err.status === 403) return 'Sin permiso: esta operación requiere rol administrador.';
    if (err.status === 400) return 'Datos inválidos: revise el formulario e intente de nuevo.';
    return err.message;
  }
  return 'No se pudo crear el dispositivo.';
}

export async function runBulkCreate(
  items: DeviceFormData[],
  opts?: BulkRunOptions,
): Promise<{ summary: BulkCreateSummary; details: DeviceDetailResponse[] }> {
  const total = items.length;
  const concurrency = Math.min(
    Math.max(Math.floor(opts?.concurrency ?? BULK_CONCURRENCY), 1),
    BULK_MAX_CONCURRENCY,
  );
  const details: DeviceDetailResponse[] = [];
  const failed: BulkItemFailure[] = [];
  let next = 0;
  let done = 0;
  const report = () => opts?.onProgress?.(done, total);

  async function worker(): Promise<void> {
    while (true) {
      if (opts?.isCancelled?.()) return;
      const index = next;
      next += 1;
      if (index >= total) return;
      if (opts?.isCancelled?.()) {
        // No se reclama como fallo: queda contabilizado como cancelado.
        done += 1;
        report();
        return;
      }
      const item = items[index];
      try {
        const created = await apiCreateDevice(toCreateDevicePayload(item));
        details.push(created);
      } catch (err) {
        failed.push({
          index,
          name: item.name,
          error: deviceErrorMessage(err),
        });
      }
      done += 1;
      report();
    }
  }

  report();
  await Promise.all(
    Array.from({ length: Math.min(concurrency, Math.max(total, 1)) }, () => worker()),
  );
  // Cancelado solo si la bandera se alzó Y quedó trabajo sin emitir: si todo
  // se emitió, el resultado es completo aunque la bandera llegue tarde.
  const emitted = details.length + failed.length;
  const cancelled = (opts?.isCancelled?.() ?? false) && emitted < total;
  return {
    summary: {
      requested: total,
      created: details.length,
      failed: failed.sort((a, b) => a.index - b.index),
      cancelled,
    },
    details,
  };
}
