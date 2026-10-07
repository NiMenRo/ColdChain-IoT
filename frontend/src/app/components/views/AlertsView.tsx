import { useState } from 'react';
import { AlertTriangle, CheckCircle, Bell, Mail, MessageSquare, Smartphone, Monitor } from 'lucide-react';
import { Button } from '../../lib/bootstrap';
import { useAuth } from '../../hooks/useAuth';
import { hasActionPermission } from '../../config/rbac';

// ─── Valid alert types (backend-aligned) ─────────────────────────────────────
type AlertType =
  | 'TEMPERATURE_EXCEEDED'
  | 'TEMPERATURE_BELOW_MIN'
  | 'HUMIDITY_ABOVE_MAX'
  | 'HUMIDITY_BELOW_MIN'
  | 'ENERGY_STATE_ANOMALY';

const ALERT_TYPE_LABEL: Record<AlertType, string> = {
  TEMPERATURE_EXCEEDED:  'Temperatura Excedida',
  TEMPERATURE_BELOW_MIN: 'Temperatura Bajo Mínimo',
  HUMIDITY_ABOVE_MAX:    'Humedad sobre Máximo',
  HUMIDITY_BELOW_MIN:    'Humedad bajo Mínimo',
  ENERGY_STATE_ANOMALY:  'Anomalía de Estado Energético',
};

interface AlertRecord {
  id: string;
  type: AlertType;
  message: string;
  deviceId: string;
  deviceName: string;
  criticality: number;
  timestamp: string;
  acknowledged: boolean;
}

const INITIAL_ALERTS: AlertRecord[] = [
  { id: 'ALT-001', type: 'TEMPERATURE_EXCEEDED',  message: 'Temperatura registrada: 6.8 °C — supera el umbral máximo de 4 °C.',   deviceId: 'DEV-003', deviceName: 'Cava Sur',       criticality: 9.2, timestamp: '2026-10-04T10:38:00', acknowledged: false },
  { id: 'ALT-002', type: 'TEMPERATURE_EXCEEDED',  message: 'Temperatura registrada: 4.1 °C — supera el umbral máximo de 4 °C.',   deviceId: 'DEV-002', deviceName: 'Vitrina Entrada',criticality: 8.1, timestamp: '2026-10-04T10:10:00', acknowledged: false },
  { id: 'ALT-003', type: 'HUMIDITY_ABOVE_MAX',    message: 'Humedad registrada: 92 % — supera el umbral máximo de 90 %.',          deviceId: 'DEV-003', deviceName: 'Cava Sur',       criticality: 7.4, timestamp: '2026-10-04T10:36:00', acknowledged: false },
  { id: 'ALT-004', type: 'ENERGY_STATE_ANOMALY',  message: 'Estado energético es OFF cuando se esperaba ON.',                       deviceId: 'DEV-004', deviceName: 'Vitrina Sala',   criticality: 6.5, timestamp: '2026-10-04T09:17:00', acknowledged: false },
  { id: 'ALT-005', type: 'TEMPERATURE_BELOW_MIN', message: 'Temperatura registrada: -0.2 °C — por debajo del umbral mínimo de 0 °C.',deviceId: 'DEV-001', deviceName: 'Cava Norte',     criticality: 5.2, timestamp: '2026-10-03T22:41:00', acknowledged: true  },
  { id: 'ALT-006', type: 'HUMIDITY_BELOW_MIN',    message: 'Humedad registrada: 83 % — por debajo del umbral mínimo de 85 %.',     deviceId: 'DEV-005', deviceName: 'Cava Central',   criticality: 4.1, timestamp: '2026-10-03T20:15:00', acknowledged: true  },
  { id: 'ALT-007', type: 'HUMIDITY_ABOVE_MAX',    message: 'Humedad registrada: 91 % — supera el umbral máximo de 90 %.',          deviceId: 'DEV-002', deviceName: 'Vitrina Entrada',criticality: 5.8, timestamp: '2026-10-03T18:22:00', acknowledged: false },
  { id: 'ALT-008', type: 'ENERGY_STATE_ANOMALY',  message: 'Estado energético es OFF cuando se esperaba ON.',                       deviceId: 'DEV-006', deviceName: 'Vitrina Back',   criticality: 3.9, timestamp: '2026-10-03T16:00:00', acknowledged: true  },
];

// ─── Notifications (separate from alerts) ────────────────────────────────────
type NotifChannel = 'dashboard' | 'email' | 'sms' | 'push';
type NotifStatus  = 'pending' | 'sent' | 'failed';

interface NotifRecord {
  id: string;
  alertId: string;
  alertLabel: string;
  channel: NotifChannel;
  status: NotifStatus;
  timestamp: string;
}

const CHANNEL_ICON: Record<NotifChannel, React.ElementType> = {
  dashboard: Monitor,
  email:     Mail,
  sms:       MessageSquare,
  push:      Smartphone,
};

const NOTIF_STATUS_CONFIG: Record<NotifStatus, { label: string; color: string; bg: string }> = {
  sent:    { label: 'Enviado',   color: '#16835B', bg: '#EAF6EF' },
  pending: { label: 'Pendiente', color: '#965D00', bg: '#FFF5E3' },
  failed:  { label: 'Fallido',   color: '#B22F2F', bg: '#FCEEEE' },
};

const NOTIFICATIONS: NotifRecord[] = [
  { id: 'NOT-001', alertId: 'ALT-001', alertLabel: 'Temperatura Excedida · Cava Sur',        channel: 'dashboard', status: 'sent',    timestamp: '2026-10-04T10:38:05' },
  { id: 'NOT-002', alertId: 'ALT-001', alertLabel: 'Temperatura Excedida · Cava Sur',        channel: 'email',     status: 'sent',    timestamp: '2026-10-04T10:38:08' },
  { id: 'NOT-003', alertId: 'ALT-001', alertLabel: 'Temperatura Excedida · Cava Sur',        channel: 'sms',       status: 'failed',  timestamp: '2026-10-04T10:38:09' },
  { id: 'NOT-004', alertId: 'ALT-003', alertLabel: 'Humedad sobre Máximo · Cava Sur',        channel: 'dashboard', status: 'sent',    timestamp: '2026-10-04T10:36:02' },
  { id: 'NOT-005', alertId: 'ALT-004', alertLabel: 'Anomalía Energética · Vitrina Sala',     channel: 'push',      status: 'pending', timestamp: '2026-10-04T09:17:11' },
  { id: 'NOT-006', alertId: 'ALT-002', alertLabel: 'Temperatura Excedida · Vitrina Entrada', channel: 'email',     status: 'sent',    timestamp: '2026-10-04T10:10:03' },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────
function formatTs(ts: string) {
  return new Date(ts).toLocaleString('es-CO', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

type ActiveTab = 'alerts' | 'notifications';
type AlertFilter = 'all' | AlertType;

export function AlertsView() {
  const { role } = useAuth();
  const canAcknowledge = hasActionPermission(role, 'acknowledgeAlert');
  const [alerts, setAlerts]   = useState(INITIAL_ALERTS);
  const [tab, setTab]         = useState<ActiveTab>('alerts');
  const [filter, setFilter]   = useState<AlertFilter>('all');

  const acknowledge = (id: string) =>
    setAlerts(prev => prev.map(a => a.id === id ? { ...a, acknowledged: true } : a));

  const pending     = alerts.filter(a => !a.acknowledged);
  const criticals   = pending.filter(a => a.criticality >= 7);
  const acknowledged = alerts.filter(a => a.acknowledged);

  const filtered = filter === 'all' ? alerts : alerts.filter(a => a.type === filter);

  const tabStyle = (active: boolean) => ({
    padding: '8px 20px', fontSize: 13, fontWeight: active ? 600 : 400, cursor: 'pointer', border: 'none',
    borderBottom: `2px solid ${active ? '#123B5D' : 'transparent'}`,
    background: 'transparent', color: active ? '#123B5D' : '#52616B',
  });

  return (
    <div>
      <h1 className="mb-1" style={{ fontSize: 20, fontWeight: 600 }}>Alertas y Notificaciones</h1>
      <p className="text-muted small mb-4">Gestión centralizada de eventos del sistema de cadena de frío.</p>

      {/* Summary cards */}
      <div className="row g-3 mb-4">
        {[
          { label: 'Sin reconocer',   value: pending.length,      bg: '#FFF5E3', color: '#965D00', border: '#ffda6a', Icon: AlertTriangle },
          { label: 'Críticas activas',value: criticals.length,    bg: '#FCEEEE', color: '#B22F2F', border: '#f1aeb5', Icon: AlertTriangle },
          { label: 'Reconocidas',     value: acknowledged.length, bg: '#EAF6EF', color: '#16835B', border: '#a3cfbb', Icon: CheckCircle   },
        ].map(s => (
          <div key={s.label} className="col-12 col-sm-4">
            <div className="rounded-3 p-3 d-flex align-items-center gap-3"
              style={{ background: s.bg, border: `1px solid ${s.border}` }}>
              <s.Icon size={26} color={s.color} />
              <div>
                <div style={{ fontSize: 28, fontWeight: 700, lineHeight: 1, color: s.color }}>{s.value}</div>
                <div style={{ fontSize: 13, marginTop: 2, color: s.color }}>{s.label}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="d-flex border-bottom mb-4">
        <button style={tabStyle(tab === 'alerts')}       onClick={() => setTab('alerts')}>
          <AlertTriangle size={14} className="me-1" style={{ verticalAlign: 'middle' }} />Alertas
        </button>
        <button style={tabStyle(tab === 'notifications')} onClick={() => setTab('notifications')}>
          <Bell size={14} className="me-1" style={{ verticalAlign: 'middle' }} />Notificaciones
        </button>
      </div>

      {/* ── ALERTS TAB ── */}
      {tab === 'alerts' && (
        <>
          {/* Type filter */}
          <div className="d-flex flex-wrap gap-2 mb-4">
            {(['all', ...Object.keys(ALERT_TYPE_LABEL)] as AlertFilter[]).map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className="rounded-2 border px-3 py-1"
                style={{ fontSize: 12, fontWeight: filter === f ? 600 : 400, cursor: 'pointer',
                  background: filter === f ? '#123B5D' : '#fff',
                  color:      filter === f ? '#fff'    : '#52616B',
                  borderColor: filter === f ? '#123B5D' : '#D9E2E8',
                }}>
                {f === 'all' ? 'Todas' : ALERT_TYPE_LABEL[f as AlertType]}
              </button>
            ))}
          </div>

          <div className="d-flex flex-column gap-2">
            {filtered.length === 0 ? (
              <div className="cc-card p-5 text-center text-muted small">
                Sin alertas registradas en el periodo seleccionado.
              </div>
            ) : filtered.map(alert => {
              const isCritical = alert.criticality >= 7;
              const borderColor = isCritical && !alert.acknowledged ? '#C83B3B' : alert.acknowledged ? '#a3cfbb' : '#ffda6a';
              const bgColor     = isCritical && !alert.acknowledged ? '#FCEEEE' : alert.acknowledged ? '#f8fdfb' : '#FFF5E3';
              return (
                <div key={alert.id} className="rounded-3 p-3"
                  style={{
                    border: `1px solid ${borderColor}`,
                    borderLeft: `4px solid ${borderColor}`,
                    background: bgColor,
                    opacity: alert.acknowledged ? 0.75 : 1,
                  }}>
                  <div className="d-flex align-items-start gap-3">
                    <div className="rounded-3 p-2 flex-shrink-0"
                      style={{ background: isCritical && !alert.acknowledged ? '#FCEEEE' : '#fff', color: isCritical ? '#B22F2F' : '#965D00' }}>
                      <AlertTriangle size={17} />
                    </div>
                    <div className="flex-grow-1">
                      <div className="d-flex justify-content-between align-items-start gap-3 flex-wrap">
                        <div className="d-flex align-items-center gap-2 flex-wrap">
                          <span className="fw-bold" style={{ fontSize: 14 }}>
                            {ALERT_TYPE_LABEL[alert.type]}
                          </span>
                          {isCritical && !alert.acknowledged && (
                            <span className="rounded-pill px-2"
                              style={{ fontSize: 11, fontWeight: 700, background: '#C83B3B', color: '#fff' }}>
                              Crítica · {alert.criticality}
                            </span>
                          )}
                          {!isCritical && !alert.acknowledged && (
                            <span className="rounded-pill px-2"
                              style={{ fontSize: 11, background: '#FFF5E3', color: '#965D00', border: '1px solid #ffda6a' }}>
                              Criticidad · {alert.criticality}
                            </span>
                          )}
                        </div>
                        <span className="small text-muted text-nowrap">{formatTs(alert.timestamp)}</span>
                      </div>
                      <div style={{ fontSize: 13, margin: '4px 0 6px' }}>{alert.message}</div>
                      <div className="d-flex justify-content-between align-items-center flex-wrap gap-2">
                        <span style={{ fontSize: 12, fontWeight: 500, color: '#52616B' }}>
                          Dispositivo: <strong>{alert.deviceName}</strong> <span className="font-monospace">({alert.deviceId})</span>
                        </span>
                        {!alert.acknowledged && canAcknowledge ? (
                          <Button variant="outline-secondary" size="sm"
                            className="d-flex align-items-center gap-1" style={{ fontSize: 12 }}
                            onClick={() => acknowledge(alert.id)}>
                            <CheckCircle size={13} />Reconocer alerta
                          </Button>
                        ) : alert.acknowledged ? (
                          <span className="d-flex align-items-center gap-1 small fw-medium" style={{ color: '#16835B' }}>
                            <CheckCircle size={13} />Reconocida
                          </span>
                        ) : null}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* ── NOTIFICATIONS TAB ── */}
      {tab === 'notifications' && (
        <>
          <p className="text-muted small mb-4">
            Registros de notificaciones asociadas a alertas. Representan el estado del canal de entrega, no confirman la recepción real por el destinatario.
          </p>
          <div className="cc-card overflow-hidden">
            <table className="w-100" style={{ borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#F5F8FA' }}>
                  <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Canal</th>
                  <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Estado</th>
                  <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Fecha</th>
                  <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Alerta relacionada</th>
                </tr>
              </thead>
              <tbody>
                {NOTIFICATIONS.map((n, i) => {
                  const ChannelIcon = CHANNEL_ICON[n.channel];
                  const ns = NOTIF_STATUS_CONFIG[n.status];
                  return (
                    <tr key={n.id} style={{ borderTop: '1px solid #EFF4F7', background: i % 2 === 1 ? '#FAFBFC' : '#fff' }}>
                      <td className="px-4 py-3">
                        <div className="d-flex align-items-center gap-2">
                          <ChannelIcon size={15} style={{ color: '#1F6F8B' }} />
                          <span className="fw-medium text-capitalize">{n.channel}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded-pill px-2 py-1 fw-semibold"
                          style={{ fontSize: 12, background: ns.bg, color: ns.color }}>
                          {ns.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-muted font-monospace" style={{ fontSize: 12 }}>
                        {formatTs(n.timestamp)}
                      </td>
                      <td className="px-4 py-3 text-muted" style={{ fontSize: 12 }}>
                        {n.alertLabel}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
