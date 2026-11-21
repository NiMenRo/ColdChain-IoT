import { useCallback, useEffect, useRef, useState } from 'react';
import { apiGetAcquisitionStatus } from '../../services/api/acquisition';
import { DASHBOARD_POLL_MS, usePolling } from './usePolling';

export type MqttStatus = 'loading' | 'connected' | 'disconnected' | 'unknown' | 'error';

export function useMqttStatus(): MqttStatus {
  const [status, setStatus] = useState<MqttStatus>('loading');
  const [attempt, setAttempt] = useState(0);
  const busy = useRef(false);
  usePolling(true, DASHBOARD_POLL_MS, useCallback(() => {
    setAttempt(n => n + 1);
  }, []), busy);

  useEffect(() => {
    let cancelled = false;
    busy.current = true;
    apiGetAcquisitionStatus().then(result => {
      if (!cancelled) {
        setStatus(result.connected === true ? 'connected'
          : result.connected === false ? 'disconnected' : 'unknown');
      }
    }).catch(() => {
      // An unavailable API is not evidence of an MQTT disconnection (or connection).
      if (!cancelled) setStatus('error');
    }).finally(() => {
      if (!cancelled) busy.current = false;
    });
    return () => {
      cancelled = true;
      busy.current = false;
    };
  }, [attempt]);
  return status;
}
