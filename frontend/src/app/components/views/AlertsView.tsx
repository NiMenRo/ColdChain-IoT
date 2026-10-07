import { useState } from 'react';
import { AlertTriangle, CheckCircle, Bell, Mail, MessageSquare, Smartphone, Monitor, Activity } from 'lucide-react';
import { Button } from '../../lib/bootstrap';
import { useAuth } from '../../hooks/useAuth';
import { hasActionPermission } from '../../config/rbac';
import {
  ALERT_TYPES,
  alertLabel,
  formatTs,
  useAlertsData,
  type AlertFilter,
} from '../../hooks/useAlertsData';

// ─── Notification channel/status visuals (backend enums; fallback neutro) ────
const CHANNEL_ICON: Record<string, React.ElementType> = {
  dashboard: Monitor,
  email:     Mail,
  sms:       MessageSquare,
  push:      Smartphone,
};

const NOTIF_STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  sent:    { label: 'Enviado',   color: '#16835B', bg: '#EAF6EF' },
  pending: { label: 'Pendiente', color: '#965D00', bg: '#FFF5E3' },
  failed:  { label: 'Fallido',   color: '#B22F2F', bg: '#FCEEEE' },
};

function channelIcon(channel: string): React.ElementType {
  return CHANNEL_ICON[channel] ?? Bell;
}

function notifStatus(status: string): { label: string; color: string; bg: string } {
  return NOTIF_STATUS_CONFIG[status] ?? { label: status, color: '#52616B', bg: '#EFF4F7' };
}

type ActiveTab = 'alerts' | 'events' | 'notifications';

export function AlertsView() {
  const { role } = useAuth();
  const canAcknowledge = hasActionPermission(role, 'acknowledgeAlert');
  const [tab, setTab] = useState<ActiveTab>('alerts');
  const data = useAlertsData();
  const {
    alerts, pendingCount, criticalCount, acknowledgedCount,
    eventsSummary, criticalSessionAlerts, sessionEvents,
    notifications, ackingId, ackError, acknowledge,
    filter, setFilter,
  } = data;

  const tabStyle = (active: boolean) => ({
    padding: '8px 20px', fontSize: 13, fontWeight: active ? 600 : 400, cursor: 'pointer', border: 'none',
    borderBottom: `2px solid ${active ? '#123B5D' : 'transparent'}`,
    background: 'transparent', color: active ? '#123B5D' : '#52616B',
  });

  return (
    <div>
      <h1 className="mb-1" style={{ fontSize: 20, fontWeight: 600 }}>Alertas y Notificaciones</h1>
      <p className="text-muted small mb-4">Gestión centralizada de eventos del sistema de cadena de frío.</p>

      {(data.isAuthBlocked || data.isConfigMissing) && !data.isLoading && (
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-3 rounded-3 px-4 py-3 mb-4"
          style={{ background: '#FFF5E3', border: '1px solid #ffda6a', borderLeft: '4px solid #C47A00' }}>
          <p className="mb-0 small">
            <strong>Datos en vivo no disponibles.</strong>{' '}
            {data.isConfigMissing
              ? 'Falta configurar VITE_API_BASE_URL en el frontend.'
              : 'La API requiere autenticación Bearer y el login actual es mock (integración de autenticación pendiente).'}
          </p>
          <button
            onClick={data.retry}
            className="border-0 bg-transparent fw-semibold"
            style={{ fontSize: 13, color: '#965D00', cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            Reintentar
          </button>
        </div>
      )}

      {/* Summary cards (fuente: GET /history/alerts) */}
      <div className="row g-3 mb-4">
        {[
          { label: 'Sin reconocer',   value: data.isLoading ? '…' : pendingCount,      bg: '#FFF5E3', color: '#965D00', border: '#ffda6a', Icon: AlertTriangle },
          { label: 'Críticas activas',value: data.isLoading ? '…' : criticalCount,     bg: '#FCEEEE', color: '#B22F2F', border: '#f1aeb5', Icon: AlertTriangle },
          { label: 'Reconocidas',     value: data.isLoading ? '…' : acknowledgedCount, bg: '#EAF6EF', color: '#16835B', border: '#a3cfbb', Icon: CheckCircle   },
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
        <button style={tabStyle(tab === 'alerts')} onClick={() => setTab('alerts')}>
          <AlertTriangle size={14} className="me-1" style={{ verticalAlign: 'middle' }} />Alertas
        </button>
        <button style={tabStyle(tab === 'events')} onClick={() => setTab('events')}>
          <Activity size={14} className="me-1" style={{ verticalAlign: 'middle' }} />Eventos
        </button>
        <button style={tabStyle(tab === 'notifications')} onClick={() => setTab('notifications')}>
          <Bell size={14} className="me-1" style={{ verticalAlign: 'middle' }} />Notificaciones
        </button>
      </div>

      {/* ── ALERTS TAB (GET /history/alerts, persistido) ── */}
      {tab === 'alerts' && (
        <>
          {/* Type filter (server-side vía query `type`) */}
          <div className="d-flex flex-wrap gap-2 mb-4">
            {(['all', ...ALERT_TYPES] as AlertFilter[]).map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className="rounded-2 border px-3 py-1"
                style={{ fontSize: 12, fontWeight: filter === f ? 600 : 400, cursor: 'pointer',
                  background: filter === f ? '#123B5D' : '#fff',
                  color:      filter === f ? '#fff'    : '#52616B',
                  borderColor: filter === f ? '#123B5D' : '#D9E2E8',
                }}>
                {f === 'all' ? 'Todas' : alertLabel(f)}
              </button>
            ))}
          </div>

          {ackError && (
            <div className="rounded-3 px-3 py-2 mb-3 small" style={{ background: '#FCEEEE', border: '1px solid #f1aeb5', color: '#B22F2F' }}>
              {ackError}
            </div>
          )}

          <div className="d-flex flex-column gap-2">
            {data.alertsStatus === 'loading' ? (
              <div className="cc-card p-5 text-center text-muted small">Cargando alertas…</div>
            ) : data.alertsStatus === 'error' ? (
              <div className="cc-card p-5 text-center small" style={{ color: '#B22F2F' }}>
                No se pudieron cargar las alertas. <button onClick={data.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
              </div>
            ) : alerts.length === 0 ? (
              <div className="cc-card p-5 text-center text-muted small">
                Sin alertas registradas en el periodo seleccionado.
              </div>
            ) : alerts.map(alert => {
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
                            {alert.label}
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
                          Dispositivo: <strong>{alert.deviceName}</strong> <span className="font-monospace">({alert.deviceId.slice(0, 8)})</span>
                        </span>
                        {!alert.acknowledged && canAcknowledge ? (
                          <Button variant="outline-secondary" size="sm"
                            className="d-flex align-items-center gap-1" style={{ fontSize: 12 }}
                            disabled={ackingId === alert.id}
                            onClick={() => acknowledge(alert.id)}>
                            <CheckCircle size={13} />{ackingId === alert.id ? 'Reconociendo…' : 'Reconocer alerta'}
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

      {/* ── EVENTS TAB (endpoints /events/*, sesión runtime del backend) ── */}
      {tab === 'events' && (
        <>
          <p className="text-muted small mb-4">
            Eventos de la sesión actual del backend (runtime, no persistido). El historial persistido está en la pestaña Alertas.
          </p>
          {data.sessionStatus === 'loading' ? (
            <div className="cc-card p-5 text-center text-muted small">Cargando eventos…</div>
          ) : data.sessionStatus === 'error' ? (
            <div className="cc-card p-5 text-center small" style={{ color: '#B22F2F' }}>
              No se pudieron cargar los eventos de sesión. <button onClick={data.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
            </div>
          ) : (
            <>
              <div className="row g-3 mb-4">
                {[
                  { label: 'Alertas en sesión', value: eventsSummary?.total_alerts ?? 0 },
                  { label: 'Eventos en sesión', value: eventsSummary?.total_events ?? 0 },
                  { label: 'Críticas en sesión', value: criticalSessionAlerts.length },
                ].map(s => (
                  <div key={s.label} className="col-12 col-sm-4">
                    <div className="rounded-3 p-3" style={{ background: '#EFF4F7', border: '1px solid #D9E2E8' }}>
                      <div style={{ fontSize: 24, fontWeight: 700, color: '#123B5D' }}>{s.value}</div>
                      <div style={{ fontSize: 13, color: '#52616B' }}>{s.label}</div>
                    </div>
                  </div>
                ))}
              </div>

              <h2 className="fw-semibold mb-2" style={{ fontSize: 15 }}>Alertas críticas de la sesión</h2>
              {criticalSessionAlerts.length === 0 ? (
                <div className="cc-card p-4 text-center text-muted small mb-4">Sin alertas críticas en la sesión actual.</div>
              ) : (
                <div className="d-flex flex-column gap-2 mb-4">
                  {criticalSessionAlerts.map(a => (
                    <div key={a.id} className="rounded-3 p-3" style={{ border: '1px solid #f1aeb5', borderLeft: '4px solid #C83B3B', background: '#FCEEEE' }}>
                      <div className="d-flex justify-content-between gap-2 flex-wrap">
                        <span className="fw-bold" style={{ fontSize: 13 }}>{alertLabel(a.type)} · {a.criticality}</span>
                        <span className="small text-muted">{formatTs(a.created_at)}</span>
                      </div>
                      <div className="text-muted" style={{ fontSize: 12 }}>{a.message}</div>
                    </div>
                  ))}
                </div>
              )}

              <h2 className="fw-semibold mb-2" style={{ fontSize: 15 }}>Eventos detectados</h2>
              {sessionEvents.length === 0 ? (
                <div className="cc-card p-4 text-center text-muted small">Sin eventos en la sesión actual.</div>
              ) : (
                <div className="cc-card overflow-hidden">
                  <table className="w-100" style={{ borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr style={{ background: '#F5F8FA' }}>
                        <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Evento</th>
                        <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Dispositivo</th>
                        <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Valor observado</th>
                        <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Detectado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sessionEvents.map((e, i) => (
                        <tr key={e.id} style={{ borderTop: '1px solid #EFF4F7', background: i % 2 === 1 ? '#FAFBFC' : '#fff' }}>
                          <td className="px-4 py-3">
                            <div className="fw-medium">{e.event_type}</div>
                            <div className="text-muted" style={{ fontSize: 12 }}>{e.message}</div>
                          </td>
                          <td className="px-4 py-3 font-monospace" style={{ fontSize: 12 }}>{e.device_code}</td>
                          <td className="px-4 py-3" style={{ fontSize: 12 }}>{String(e.observed_value)}</td>
                          <td className="px-4 py-3 text-muted font-monospace" style={{ fontSize: 12 }}>{formatTs(e.detected_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </>
      )}

      {/* ── NOTIFICATIONS TAB (GET /notifications/history) ── */}
      {tab === 'notifications' && (
        <>
          <p className="text-muted small mb-4">
            Registros de notificaciones asociadas a alertas. Representan el estado del canal de entrega, no confirman la recepción real por el destinatario.
          </p>
          {data.notificationsStatus === 'loading' ? (
            <div className="cc-card p-5 text-center text-muted small">Cargando notificaciones…</div>
          ) : data.notificationsStatus === 'error' ? (
            <div className="cc-card p-5 text-center small" style={{ color: '#B22F2F' }}>
              No se pudieron cargar las notificaciones. <button onClick={data.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
            </div>
          ) : notifications.length === 0 ? (
            <div className="cc-card p-5 text-center text-muted small">Sin notificaciones registradas.</div>
          ) : (
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
                  {notifications.map((n, i) => {
                    const ChannelIcon = channelIcon(n.channel);
                    const ns = notifStatus(n.status);
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
                          {formatTs(n.notification_date)}
                        </td>
                        <td className="px-4 py-3 text-muted" style={{ fontSize: 12 }}>
                          {n.alert ? `${alertLabel(n.alert.type)} · Criticidad ${n.alert.criticality}` : n.alert_id.slice(0, 8)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
