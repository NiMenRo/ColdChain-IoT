// Contador de notificaciones no leídas para la campana (fase C).
//
// Diseño anti-duplicación:
// - Este hook consulta SOLO GET /notifications/unread-count (un entero,
//   sin listas). Es la única fuente del punto rojo global.
// - AlertsView NO llama a este endpoint: deriva su conteo del historial
//   persistente que ya trae por página. Ninguna URL se pide dos veces.
// - Tras marcar lecturas, AlertsView emite NOTIFICATIONS_CHANGED_EVENT y
//   este hook refresca de inmediato (sin acortar el polling).
// - Polling ligero reutilizando usePolling (pausa con pestaña oculta).

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  NOTIFICATIONS_CHANGED_EVENT,
  apiGetUnreadCount,
} from '../../services/api/notifications';
import { ALERTS_POLL_MS, usePolling } from './usePolling';

export function useUnreadCount(): { unread: number; refresh: () => void } {
  const [unread, setUnread] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const busyRef = useRef(false);
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const refresh = useCallback(() => setAttempt((n) => n + 1), []);

  // Ticks periódicos (fondo) + refresco inmediato tras marcar lecturas.
  usePolling(true, ALERTS_POLL_MS, useCallback(() => {
    setAttempt((n) => n + 1);
  }, []), busyRef);

  useEffect(() => {
    const onChanged = () => setAttempt((n) => n + 1);
    window.addEventListener(NOTIFICATIONS_CHANGED_EVENT, onChanged);
    return () => window.removeEventListener(NOTIFICATIONS_CHANGED_EVENT, onChanged);
  }, []);

  useEffect(() => {
    let cancelled = false;
    busyRef.current = true;
    apiGetUnreadCount()
      .then((res) => {
        if (cancelled || !mountedRef.current) return;
        busyRef.current = false;
        const value = Number(res?.unread);
        setUnread(Number.isFinite(value) && value > 0 ? Math.floor(value) : 0);
      })
      .catch(() => {
        // La campana conserva el último valor conocido; sin ruido visual.
        if (!cancelled && mountedRef.current) busyRef.current = false;
      });
    return () => {
      cancelled = true;
      busyRef.current = false;
    };
  }, [attempt]);

  return { unread, refresh };
}
