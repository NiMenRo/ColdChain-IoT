/**
 * Unidades reales de las métricas QoS del backend.
 *
 * El backend persiste latencia/jitter en SEGUNDOS (total_seconds) y la UI
 * histórica los mostraba rotulados como "ms": un valor de 18000 equivale a
 * ~5 h de desfase, no a 18 s. Toda visualización convierte s → ms aquí.
 * pdr/packet_loss son %; throughput son bytes/s (B/s, no Mbps).
 * Solo formato de presentación; ningún cálculo ni agregación.
 */

function adaptive(value: number, bigDigits: number, midDigits: number, smallDigits: number): string {
  const abs = Math.abs(value);
  const digits = abs >= 100 ? bigDigits : abs >= 1 ? midDigits : smallDigits;
  return value.toLocaleString('es-CO', { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

/** Segundos (backend) → milisegundos (pantalla). */
export function secondsToMs(seconds: number): number {
  return seconds * 1000;
}

/** Formatea un valor YA en ms con decimales adaptativos. */
export function formatMsValue(ms: number): string {
  return `${adaptive(ms, 0, 1, 2)} ms`;
}

/** Formatea segundos del backend directamente como ms. */
export function formatMs(seconds: number): string {
  return formatMsValue(secondsToMs(seconds));
}

/** Throughput del backend (bytes/s) con decimales visibles. */
export function formatThroughput(bps: number): string {
  return `${adaptive(bps, 1, 1, 3)} B/s`;
}

/** Redondea artefactos float (p. ej. 260.47999999999996) a 3 decimales máximo. */
export function roundMax3(v: number): number {
  return Math.round(v * 1000) / 1000;
}
