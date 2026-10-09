import { useNavigate } from 'react-router';
import { Thermometer, Droplets, Zap, AlertTriangle, Cpu, ArrowRight, ChevronRight, Snowflake, Activity, CheckCircle, Clock } from 'lucide-react';
import { Card, Row, Col, Badge } from '../../lib/bootstrap';
import { useDevices, DEVICE_TYPE_LABEL } from '../../contexts/DeviceContext';
import { useAuth } from '../../hooks/useAuth';
import { useDashboardData } from '../../hooks/useDashboardData';
import { SIDEBAR_ROLES } from '../../config/rbac';

export function DashboardView() {
  const { devices } = useDevices();
  const { role } = useAuth();
  const navigate = useNavigate();
  const dash = useDashboardData();

  const total = dash.totalDevices;
  const active = dash.activeDevices;
  const errored = dash.errorDevices ?? 0;

  const avgTemp = dash.avgTemp;
  const avgHumidity = dash.avgHumidity;
  // Sin fuente agregada real de energía en el backend (las lecturas exponen
  // energy por lectura, sin endpoint agregado): se muestra no disponible.
  const energyAvailable = false;

  const totalAlerts = dash.totalAlerts;
  const criticalAlerts = dash.criticalAlerts;

  const canSimulate = role && SIDEBAR_ROLES.simulation.includes(role);

  const tempStatus = avgTemp === null ? 'unknown' : avgTemp > 4 ? 'error' : avgTemp > 3 ? 'warning' : 'ok';
  const humStatus = avgHumidity === null ? 'unknown' : avgHumidity > 90 ? 'error' : avgHumidity > 88 ? 'warning' : 'ok';

  const connectionLabel = dash.isLoading
    ? 'Cargando datos…'
    : dash.isConfigMissing
      ? 'API no configurada'
      : dash.isAuthBlocked
        ? 'Sin conexión con la API'
        : dash.errorMessage
          ? 'Sin conexión con la API'
          : 'Datos en vivo';

  const recentAlerts = dash.recentAlerts;
  const qosCells = dash.qosCells;
  const trafficRows = dash.trafficRows;
  const trafficTotal = trafficRows.reduce((s, r) => s + r.count, 0);

  return (
    <div className="d-flex flex-column gap-4">

      {/* Header */}
      <div className="d-flex flex-wrap justify-content-between align-items-start gap-3">
        <div>
          <div className="small fw-medium text-muted mb-1" style={{ letterSpacing: '0.12em', fontSize: 11 }}>CENTRO DE MONITOREO</div>
          <h1 className="mb-1" style={{ fontSize: 28, fontWeight: 700 }}>Dashboard</h1>
          <p className="text-muted small mb-0">Vista operativa de la infraestructura de cadena de frío.</p>
        </div>
        <div className="d-flex align-items-center gap-3 pt-1">
          <span className="d-none d-sm-flex align-items-center gap-2 small text-muted">
            <Clock size={14} />{connectionLabel}
          </span>
          {canSimulate && (
            <button
              onClick={() => navigate('/app/simulation')}
              className="d-flex align-items-center gap-2 rounded-3 border-0 px-4 py-2"
              style={{ background: '#123B5D', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
            >
              Ir a simulación
            </button>
          )}
        </div>
      </div>

      {/* Aviso de dependencia de autenticación / configuración (no bloquea la vista) */}
      {(dash.isAuthBlocked || dash.isConfigMissing) && !dash.isLoading && (
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-3 rounded-3 px-4 py-3"
          style={{ background: '#FFF5E3', border: '1px solid #ffda6a', borderLeft: '4px solid #C47A00' }}>
          <p className="mb-0 small">
            <strong>Datos en vivo no disponibles.</strong>{' '}
            {dash.isConfigMissing
              ? 'Falta configurar VITE_API_BASE_URL en el frontend.'
              : 'La API requiere autenticación Bearer. Inicie sesión nuevamente si su sesión expiró.'}
            {' '}La capa de servicios ya consulta los endpoints reales; reintente cuando la API esté accesible.
          </p>
          <button
            onClick={dash.retry}
            className="d-flex align-items-center gap-2 border-0 bg-transparent fw-semibold"
            style={{ fontSize: 13, color: '#965D00', cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            Reintentar <ArrowRight size={14} />
          </button>
        </div>
      )}

      {/* Alerta crítica si hay dispositivos en error (fuente: GET /devices) */}
      {!dash.isLoading && dash.devicesStatus === 'success' && errored > 0 && (
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-3 rounded-3 px-4 py-3"
          style={{ background: '#FCEEEE', border: '1px solid #f1aeb5', borderLeft: '4px solid #C83B3B' }}>
          <div className="d-flex align-items-center gap-2">
            <AlertTriangle size={18} color="#B22F2F" style={{ flexShrink: 0 }} />
            <p className="mb-0 small">
              <strong>{errored} dispositivo{errored > 1 ? 's' : ''} en estado de error</strong> — Se requiere atención. Hay {criticalAlerts} alerta{criticalAlerts !== 1 ? 's' : ''} crítica{criticalAlerts !== 1 ? 's' : ''} sin reconocer.
            </p>
          </div>
          <button
            onClick={() => navigate('/app/alerts')}
            className="d-flex align-items-center gap-2 border-0 bg-transparent fw-semibold"
            style={{ fontSize: 13, color: '#B22F2F', cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            Revisar alertas <ArrowRight size={14} />
          </button>
        </div>
      )}

      {/* ── KPI Summary (fuente: /devices + /history/summary + /history/alerts) ── */}
      <Row className="g-3" as="section" aria-label="Resumen del entorno">
        {[
          { icon: Cpu,           label: 'Total dispositivos',   value: dash.isLoading ? '…' : total ?? '—',         suffix: '',              color: '#123B5D' },
          { icon: Snowflake,     label: 'Dispositivos activos', value: dash.isLoading ? '…' : active ?? '—',        suffix: total !== null && active !== null ? `/ ${total}` : '',   color: '#16835B' },
          { icon: AlertTriangle, label: 'Alertas activas',      value: dash.isLoading ? '…' : totalAlerts ?? '—',   suffix: '',              color: '#C47A00' },
          { icon: AlertTriangle, label: 'Alertas críticas',     value: dash.isLoading ? '…' : criticalAlerts,       suffix: '',              color: '#C83B3B' },
        ].map(m => (
          <Col key={m.label} xs={6} xl={3}>
            <Card className="cc-stat-card h-100 p-1">
              <Card.Body>
                <div className="d-flex justify-content-between align-items-center text-muted mb-3">
                  <span className="small fw-medium">{m.label}</span>
                  <m.icon size={18} style={{ color: m.color }} />
                </div>
                <div className="d-flex align-items-baseline gap-2 mb-1">
                  <span className="cc-stat-value" style={{ color: m.color }}>{m.value}</span>
                  {m.suffix && <span className="small text-muted">{m.suffix}</span>}
                </div>
              </Card.Body>
            </Card>
          </Col>
        ))}
      </Row>

      {/* ── Condiciones ambientales (fuente: /history/readings/trends) ── */}
      <Card className="cc-card" as="section" aria-label="Condiciones ambientales">
        <div className="d-flex flex-wrap justify-content-between align-items-center border-bottom px-4 py-3 gap-3">
          <h2 className="d-flex align-items-center gap-2 mb-0 small fw-semibold" style={{ fontSize: 15 }}>
            <Snowflake size={17} style={{ color: '#1F6F8B' }} />Condiciones ambientales
          </h2>
          <span className="small text-muted">Promedio agregado por el backend (tendencias por hora)</span>
        </div>
        <Row className="g-0">
          {/* Temperatura */}
          <Col xs={12} sm={4} className="p-4" style={{ borderRight: '1px solid #D9E2E8' }}>
            <div className="d-flex align-items-center gap-2 text-muted small mb-3">
              <Thermometer size={16} />Temperatura promedio
            </div>
            {dash.ambientStatus === 'loading' ? (
              <div className="small text-muted">Cargando…</div>
            ) : dash.ambientStatus === 'error' ? (
              <div className="small" style={{ color: '#B22F2F' }}>
                No se pudo cargar. <button onClick={dash.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
              </div>
            ) : (
              <>
                <div className="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-2">
                  <div className="d-flex align-items-baseline gap-1">
                    <span className="cc-stat-value" style={{ fontSize: '1.7rem' }}>{avgTemp !== null ? avgTemp.toFixed(1) : '—'}</span>
                    <span className="small text-muted">°C</span>
                  </div>
                  <span className={`fw-semibold rounded-pill px-2 py-1`} style={{ fontSize: 12,
                    background: tempStatus === 'error' ? '#FCEEEE' : tempStatus === 'warning' ? '#FFF5E3' : tempStatus === 'unknown' ? '#EFF4F7' : '#EAF6EF',
                    color:      tempStatus === 'error' ? '#B22F2F' : tempStatus === 'warning' ? '#965D00' : tempStatus === 'unknown' ? '#52616B' : '#16835B',
                  }}>
                    {tempStatus === 'error' ? '— Crítico' : tempStatus === 'warning' ? '— Advertencia' : tempStatus === 'unknown' ? '— Sin datos' : '— Normal'}
                  </span>
                </div>
                <p className="mb-0 text-muted" style={{ fontSize: 11 }}>Umbral: 0 °C – 4 °C</p>
              </>
            )}
          </Col>
          {/* Humedad */}
          <Col xs={12} sm={4} className="p-4" style={{ borderRight: '1px solid #D9E2E8' }}>
            <div className="d-flex align-items-center gap-2 text-muted small mb-3">
              <Droplets size={16} />Humedad promedio
            </div>
            {dash.ambientStatus === 'loading' ? (
              <div className="small text-muted">Cargando…</div>
            ) : dash.ambientStatus === 'error' ? (
              <div className="small" style={{ color: '#B22F2F' }}>
                No se pudo cargar. <button onClick={dash.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
              </div>
            ) : (
              <>
                <div className="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-2">
                  <div className="d-flex align-items-baseline gap-1">
                    <span className="cc-stat-value" style={{ fontSize: '1.7rem' }}>{avgHumidity !== null ? avgHumidity.toFixed(0) : '—'}</span>
                    <span className="small text-muted">%</span>
                  </div>
                  <span className="fw-semibold rounded-pill px-2 py-1" style={{ fontSize: 12,
                    background: humStatus === 'error' ? '#FCEEEE' : humStatus === 'warning' ? '#FFF5E3' : humStatus === 'unknown' ? '#EFF4F7' : '#EAF6EF',
                    color:      humStatus === 'error' ? '#B22F2F' : humStatus === 'warning' ? '#965D00' : humStatus === 'unknown' ? '#52616B' : '#16835B',
                  }}>
                    {humStatus === 'error' ? '— Crítico' : humStatus === 'warning' ? '— Advertencia' : humStatus === 'unknown' ? '— Sin datos' : '— Normal'}
                  </span>
                </div>
                <p className="mb-0 text-muted" style={{ fontSize: 11 }}>Umbral: 85 % – 90 %</p>
              </>
            )}
          </Col>
          {/* Energía */}
          <Col xs={12} sm={4} className="p-4">
            <div className="d-flex align-items-center gap-2 text-muted small mb-3">
              <Zap size={16} />Estado energético
            </div>
            <div className="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-2">
              <div className="d-flex align-items-baseline gap-1">
                <span className="cc-stat-value" style={{ fontSize: '1.7rem', color: '#52616B' }}>
                  {energyAvailable ? '' : '—'}
                </span>
                <span className="small text-muted">{energyAvailable ? '' : 'No disponible'}</span>
              </div>
              <span className="fw-semibold rounded-pill px-2 py-1" style={{ fontSize: 12, background: '#EFF4F7', color: '#52616B' }}>
                — Sin fuente agregada
              </span>
            </div>
            <p className="mb-0 text-muted" style={{ fontSize: 11 }}>El backend no expone agregado de energía; no se deriva en frontend.</p>
          </Col>
        </Row>
      </Card>

      {/* ── Actividad reciente + Tráfico ── */}
      <Row className="g-4">
        {/* Alertas recientes (fuente: /history/alerts) */}
        <Col xs={12} xl={7}>
          <Card className="cc-card h-100 d-flex flex-column">
            <div className="d-flex justify-content-between align-items-center border-bottom px-4 py-3">
              <div>
                <h2 className="mb-0 fw-semibold" style={{ fontSize: 15 }}>Alertas recientes</h2>
                <p className="mb-0 text-muted" style={{ fontSize: 12 }}>Últimos eventos registrados por el sistema</p>
              </div>
              <Badge style={{ background: '#C83B3B' }}>{criticalAlerts} crítica{criticalAlerts !== 1 ? 's' : ''}</Badge>
            </div>
            <div className="flex-grow-1 px-2">
              {dash.alertsStatus === 'loading' ? (
                <div className="text-center text-muted py-5 small">Cargando alertas…</div>
              ) : dash.alertsStatus === 'error' ? (
                <div className="text-center py-5 small" style={{ color: '#B22F2F' }}>
                  No se pudieron cargar las alertas. <button onClick={dash.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
                </div>
              ) : recentAlerts.length === 0 ? (
                <div className="text-center text-muted py-5 small">Sin alertas registradas.</div>
              ) : recentAlerts.map(alert => {
                const isCritical = alert.criticality >= 7;
                return (
                  <div key={alert.id} className="d-flex align-items-start gap-3 py-3 px-2 border-bottom"
                    style={{ opacity: alert.acknowledged ? 0.6 : 1 }}>
                    <div className="rounded-3 p-2 flex-shrink-0"
                      style={{ background: isCritical ? '#FCEEEE' : '#FFF5E3', color: isCritical ? '#B22F2F' : '#965D00' }}>
                      <AlertTriangle size={16} />
                    </div>
                    <div className="flex-grow-1">
                      <div className="d-flex justify-content-between align-items-start gap-2 flex-wrap">
                        <div className="d-flex align-items-center gap-2 flex-wrap">
                          <span className="fw-semibold" style={{ fontSize: 13 }}>{alert.label}</span>
                          {isCritical && !alert.acknowledged && (
                            <span className="rounded-pill px-2" style={{ fontSize: 11, fontWeight: 700, background: '#C83B3B', color: '#fff' }}>
                              Crítica · {alert.criticality}
                            </span>
                          )}
                          {alert.acknowledged && (
                            <span className="d-flex align-items-center gap-1" style={{ fontSize: 11, color: '#16835B' }}>
                              <CheckCircle size={11} />Reconocida
                            </span>
                          )}
                        </div>
                        <span className="small text-muted text-nowrap">{alert.timestamp}</span>
                      </div>
                      <p className="mb-0 text-muted" style={{ fontSize: 12 }}>{alert.deviceName}</p>
                    </div>
                  </div>
                );
              })}
            </div>
            <button
              onClick={() => navigate('/app/alerts')}
              className="d-flex w-100 justify-content-between align-items-center border-top border-0 bg-transparent px-4 py-3 fw-medium"
              style={{ fontSize: 13, color: '#123B5D', cursor: 'pointer' }}
            >
              Ver todas las alertas <ChevronRight size={16} />
            </button>
          </Card>
        </Col>

        {/* Distribución de tráfico (fuente: /history/summary.traffic_by_priority) */}
        <Col xs={12} xl={5}>
          <Card className="cc-card h-100 d-flex flex-column">
            <div className="border-bottom px-4 py-3">
              <h2 className="mb-0 fw-semibold" style={{ fontSize: 15 }}>Clasificación de tráfico</h2>
              <p className="mb-0 text-muted" style={{ fontSize: 12 }}>Distribución por prioridad y cola</p>
            </div>
            <div className="flex-grow-1 px-4 py-3 d-flex flex-column gap-3">
              {dash.trafficStatus === 'loading' ? (
                <div className="text-center text-muted py-5 small">Cargando tráfico…</div>
              ) : dash.trafficStatus === 'error' ? (
                <div className="text-center py-5 small" style={{ color: '#B22F2F' }}>
                  No se pudo cargar el tráfico. <button onClick={dash.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
                </div>
              ) : (
                <>
                  {trafficRows.map(row => {
                    const pct = trafficTotal > 0 ? Math.round((row.count / trafficTotal) * 100) : 0;
                    return (
                      <div key={row.priority}>
                        <div className="d-flex justify-content-between align-items-center mb-1">
                          <div className="d-flex align-items-center gap-2">
                            <span className="fw-semibold rounded-pill px-2 py-0" style={{ fontSize: 12, background: row.bg, color: row.color }}>
                              {row.priority}
                            </span>
                            <span className="text-muted" style={{ fontSize: 12 }}>→ {row.queue}</span>
                          </div>
                          <span className="small fw-semibold" style={{ color: row.color }}>{row.count} lecturas</span>
                        </div>
                        <div className="overflow-hidden rounded-pill" style={{ height: 8, background: '#EFF4F7' }}>
                          <div style={{ height: '100%', width: `${pct}%`, background: row.color, borderRadius: 4 }} />
                        </div>
                        <div className="text-muted" style={{ fontSize: 11, marginTop: 2 }}>{pct}% del total</div>
                      </div>
                    );
                  })}
                  {trafficTotal === 0 && (
                    <p className="mb-0 text-muted" style={{ fontSize: 12 }}>Sin lecturas clasificadas registradas.</p>
                  )}
                </>
              )}
              <p className="mb-0 mt-2 text-muted" style={{ fontSize: 11, borderTop: '1px solid #EFF4F7', paddingTop: 8 }}>
                La clasificación es determinada automáticamente por el sistema.
              </p>
            </div>
            <button
              onClick={() => navigate('/app/traffic')}
              className="d-flex w-100 justify-content-between align-items-center border-top border-0 bg-transparent px-4 py-3 fw-medium"
              style={{ fontSize: 13, color: '#123B5D', cursor: 'pointer' }}
            >
              Ver clasificación de tráfico <ChevronRight size={16} />
            </button>
          </Card>
        </Col>
      </Row>

      {/* ── QoS Snapshot (fuente: /history/qos/trends) ── */}
      <Card className="cc-card">
        <div className="d-flex justify-content-between align-items-center border-bottom px-4 py-3">
          <div className="d-flex align-items-center gap-2">
            <Activity size={17} style={{ color: '#1F6F8B' }} />
            <h2 className="mb-0 fw-semibold" style={{ fontSize: 15 }}>Estado QoS</h2>
          </div>
          <button
            onClick={() => navigate('/app/qos')}
            className="d-flex align-items-center gap-1 border-0 bg-transparent fw-medium"
            style={{ fontSize: 13, color: '#123B5D', cursor: 'pointer' }}
          >
            Ver análisis completo <ArrowRight size={14} />
          </button>
        </div>
        <Row className="g-0">
          {dash.qosStatus === 'loading' ? (
            <div className="p-4 small text-muted">Cargando métricas QoS…</div>
          ) : dash.qosStatus === 'error' ? (
            <div className="p-4 small" style={{ color: '#B22F2F' }}>
              No se pudieron cargar las métricas QoS. <button onClick={dash.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
            </div>
          ) : qosCells.length === 0 ? (
            <div className="p-4 small text-muted">Sin métricas QoS registradas.</div>
          ) : (
            qosCells.map((m, i) => (
              <Col key={m.label} xs={6} sm={3} className="p-4" style={{ borderRight: i < qosCells.length - 1 ? '1px solid #D9E2E8' : undefined }}>
                <div className="small text-muted mb-2">{m.label}</div>
                <div className="fw-bold" style={{ fontSize: 22, color: '#123B5D' }}>{m.value}</div>
              </Col>
            ))
          )}
        </Row>
      </Card>

      {/* ── Dispositivos (fuente: DeviceContext → GET /devices, TSK-049) ── */}
      <Card className="cc-card">
        <div className="d-flex justify-content-between align-items-center border-bottom px-4 py-3">
          <h2 className="mb-0 fw-semibold" style={{ fontSize: 15 }}>Estado de dispositivos</h2>
          <button
            onClick={() => navigate('/app/sensors')}
            className="border-0 bg-transparent"
            style={{ color: '#123B5D' }}
          >
            <ArrowRight size={18} />
          </button>
        </div>
        <div className="p-3">
          <Row className="g-2">
            {devices.map(d => {
              const statusMap = {
                active:      { label: 'Activo',       bg: '#EAF6EF', color: '#16835B', border: '#a3cfbb' },
                inactive:    { label: 'Inactivo',     bg: '#EFF4F7', color: '#52616B', border: '#D9E2E8' },
                maintenance: { label: 'Mantenimiento',bg: '#FFF5E3', color: '#965D00', border: '#ffda6a' },
                error:       { label: 'Error',        bg: '#FCEEEE', color: '#B22F2F', border: '#f1aeb5' },
              }[d.status];
              const typeLabel = DEVICE_TYPE_LABEL[d.device_type];
              return (
                <Col key={d.id} xs={12} sm={6} xl={4}>
                  <div className="rounded-3 p-3" style={{ border: `1px solid ${statusMap.border}`, background: statusMap.bg }}>
                    <div className="d-flex justify-content-between align-items-start mb-1">
                      <div>
                        <div className="fw-semibold" style={{ fontSize: 13 }}>{d.name}</div>
                        <div className="text-muted" style={{ fontSize: 11 }}>{d.id} · {typeLabel} · {d.location}</div>
                      </div>
                      <span className="fw-semibold rounded-pill px-2 py-0" style={{ fontSize: 11, color: statusMap.color, background: '#fff', border: `1px solid ${statusMap.border}` }}>
                        {statusMap.label}
                      </span>
                    </div>
                    {d.status === 'active' && (
                      <div className="d-flex gap-3 mt-2">
                        <span className="small text-muted d-flex align-items-center gap-1">
                          <Thermometer size={12} />— °C
                        </span>
                        <span className="small text-muted d-flex align-items-center gap-1">
                          <Droplets size={12} />— %
                        </span>
                        <span className="small d-flex align-items-center gap-1" style={{ color: '#52616B' }}>
                          <Zap size={12} />—
                        </span>
                      </div>
                    )}
                  </div>
                </Col>
              );
            })}
          </Row>
        </div>
      </Card>

      <footer className="d-flex flex-wrap justify-content-between align-items-center gap-2 text-muted" style={{ fontSize: 11 }}>
        <span>ColdChain-IoT · Monitoreo operativo de cadena de frío</span>
        <span className="d-flex align-items-center gap-1"><Snowflake size={12} />{dash.isLoading ? 'Conectando con la API…' : dash.errorMessage || dash.isAuthBlocked || dash.isConfigMissing ? 'API no disponible — se muestran estados por sección' : 'Datos en vivo de la API'}</span>
      </footer>
    </div>
  );
}
