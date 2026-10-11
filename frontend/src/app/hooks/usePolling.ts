import { useEffect, useRef } from 'react';

/** Intervalos de polling en segundo plano (ms). Justificación en cada hook. */
export const DASHBOARD_POLL_MS = 8000;
export const DEVICES_POLL_MS = 10000;
export const ALERTS_POLL_MS = 10000;

/**
 * Polling ligero y seguro para refrescos en segundo plano.
 *
 * - Un único intervalo por montaje (sin duplicados por renders).
 * - Pausa cuando la pestaña está oculta; refresca al volver a ser visible.
 * - Limpieza total al desmontar o deshabilitar.
 * - Nunca llama a `tick` si hay una petición en vuelo (candado `isBusyRef`
 *   que el consumidor marca alrededor de su fetch).
 *
 * El tick NO hace HTTP directamente: el consumidor decide qué refrescar
 * (misma ruta View → Hook → Servicio → apiFetch).
 */
export function usePolling(
  enabled: boolean,
  intervalMs: number,
  tick: () => void,
  isBusyRef: React.MutableRefObject<boolean>,
): void {
  const tickRef = useRef(tick);
  tickRef.current = tick;

  useEffect(() => {
    if (!enabled || intervalMs <= 0) return;

    const fire = () => {
      if (document.hidden) return;
      if (isBusyRef.current) return;
      tickRef.current();
    };

    const id = window.setInterval(fire, intervalMs);
    const onVisible = () => {
      if (!document.hidden) fire();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [enabled, intervalMs, isBusyRef]);
}
