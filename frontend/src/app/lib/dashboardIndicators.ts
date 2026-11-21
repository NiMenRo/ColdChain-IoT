import type { HistorySummary } from '../../services/api/history';

/** Global database aggregates; recent lists must never stand in for totals. */
export function dashboardIndicators(summary: HistorySummary | null) {
  return {
    totalDevices: summary?.total_devices ?? null,
    activeDevices: summary?.active_devices ?? null,
    errorDevices: summary?.error_devices ?? null,
    totalAlerts: summary?.active_alerts ?? null,
    criticalAlerts: summary?.critical_active_alerts ?? null,
  };
}
