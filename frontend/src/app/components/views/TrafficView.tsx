import { Cell, Tooltip, ResponsiveContainer, PieChart, Pie, LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts';
import { Info } from 'lucide-react';
import { Card, Row, Col } from '../../lib/bootstrap';
import { formatTs } from '../../hooks/useAlertsData';
import { useTrafficData } from '../../hooks/useTrafficData';
import { useHistoricalAnalytics } from '../../hooks/useHistoricalAnalytics';

const TICK_STYLE   = { fill: '#52616B', fontSize: 11 };
const TOOLTIP_STYLE = { border: '1px solid #D9E2E8', borderRadius: '4px', fontSize: '12px' };

export function TrafficView() {
  const data = useTrafficData();
  const { rows, total, recent } = data;
  // Análisis histórico (TSK-052): evolución y distribución de criticidad sobre
  // muestra paginada acotada; los agregados globales vienen de /history/summary.
  const hist = useHistoricalAnalytics();
  const critEvolution = [...hist.classSample]
    .sort((a, b) => (a.timestamp < b.timestamp ? -1 : 1))
    .map(c => {
      const d = new Date(c.timestamp);
      const t = Number.isNaN(d.getTime())
        ? c.timestamp
        : `${d.toLocaleDateString('es-CO', { day: '2-digit', month: '2-digit' })} ${d.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' })}`;
      return { t, criticality: c.criticality };
    });

  return (
    <div>
      <h1 className="mb-1" style={{ fontSize: 20, fontWeight: 600 }}>Clasificación de Tráfico</h1>
      <p className="text-muted small mb-1">
        Distribución y análisis de lecturas por prioridad y cola de procesamiento.
      </p>

      {/* Informational notice */}
      <div className="d-flex align-items-start gap-2 rounded-3 px-4 py-3 mb-4"
        style={{ background: '#E8F5F6', border: '1px solid #27B3C2' }}>
        <Info size={16} style={{ color: '#1F6F8B', flexShrink: 0, marginTop: 2 }} />
        <p className="mb-0 small" style={{ color: '#123B5D' }}>
          La asignación de prioridad y cola es determinada <strong>automáticamente</strong> por el sistema según la criticidad de cada lectura. No es configurable por el usuario.
        </p>
      </div>

      {(data.isAuthBlocked || data.isConfigMissing) && !data.isLoading && (
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-3 rounded-3 px-4 py-3 mb-4"
          style={{ background: '#FFF5E3', border: '1px solid #ffda6a', borderLeft: '4px solid #C47A00' }}>
          <p className="mb-0 small">
            <strong>Datos en vivo no disponibles.</strong>{' '}
            {data.isConfigMissing
              ? 'Falta configurar VITE_API_BASE_URL en el frontend.'
              : 'La API requiere autenticación Bearer. Inicie sesión nuevamente si su sesión expiró.'}
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

      {/* Summary KPIs (fuente: GET /history/summary.traffic_by_priority) */}
      <Row className="g-3 mb-4">
        {data.status === 'loading' ? (
          <div className="text-muted small px-3 py-4">Cargando distribución…</div>
        ) : data.status === 'error' ? (
          <div className="px-3 py-4 small" style={{ color: '#B22F2F' }}>
            No se pudo cargar la distribución. <button onClick={data.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
          </div>
        ) : rows.map(row => (
          <Col key={row.priority} xs={12} sm={4}>
            <div className="rounded-3 p-3" style={{ background: row.bg, border: `1px solid ${row.border}`, borderTop: `3px solid ${row.color}` }}>
              <div className="d-flex justify-content-between align-items-start mb-1">
                <span className="fw-bold rounded-pill px-2" style={{ fontSize: 12, background: row.color, color: '#fff' }}>
                  {row.priority}
                </span>
                <code style={{ fontSize: 12, color: row.color }}>{row.queue}</code>
              </div>
              <div style={{ fontSize: 28, fontWeight: 700, color: row.color }}>{row.count}</div>
              <div style={{ fontSize: 12, color: row.color }}>lecturas ({row.pct.toFixed(1)}%)</div>
            </div>
          </Col>
        ))}
      </Row>

      {/* Mapping table */}
      <Card className="cc-card mb-4">
        <div className="cc-card-header">Relación Prioridad → Cola de procesamiento</div>
        <div className="overflow-hidden">
          <table className="w-100" style={{ borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#F5F8FA' }}>
                <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Prioridad</th>
                <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Cola</th>
                <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Lecturas</th>
                <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Descripción</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={row.priority} style={{ borderTop: '1px solid #EFF4F7', background: i % 2 === 1 ? '#FAFBFC' : '#fff' }}>
                  <td className="px-4 py-3">
                    <span className="fw-bold rounded-pill px-3 py-1" style={{ fontSize: 12, background: row.bg, color: row.color, border: `1px solid ${row.border}` }}>
                      {row.priority}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <code style={{ fontSize: 13, background: '#EAF1F5', padding: '3px 8px', borderRadius: 4, color: '#123B5D' }}>
                      {row.queue}
                    </code>
                  </td>
                  <td className="px-4 py-3">
                    <div className="d-flex align-items-center gap-2">
                      <div style={{ flex: 1, height: 8, background: '#EFF4F7', borderRadius: 4, maxWidth: 80 }}>
                        <div style={{ height: '100%', width: `${row.pct}%`, background: row.color, borderRadius: 4 }} />
                      </div>
                      <span className="fw-semibold" style={{ color: row.color }}>{data.isLoading ? '…' : row.count}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-muted" style={{ fontSize: 12 }}>{row.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 py-2 border-top small text-muted">
            Total: {data.isLoading ? '…' : total} lecturas clasificadas en el periodo actual.
          </div>
        </div>
      </Card>

      <Row className="g-4">
        {/* Recent classifications (fuente: GET /history/classifications) */}
        <Col xs={12} lg={7}>
          <Card className="cc-card">
            <div className="cc-card-header">Clasificaciones recientes</div>
            {data.recentStatus === 'loading' ? (
              <div className="p-4 small text-muted">Cargando clasificaciones…</div>
            ) : data.recentStatus === 'error' ? (
              <div className="p-4 small" style={{ color: '#B22F2F' }}>
                No se pudieron cargar las clasificaciones. <button onClick={data.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
              </div>
            ) : recent.length === 0 ? (
              <div className="p-4 small text-muted">Sin clasificaciones disponibles.</div>
            ) : (
              <div className="overflow-hidden">
                <table className="w-100" style={{ borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#F5F8FA' }}>
                      <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Criticidad</th>
                      <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Prioridad</th>
                      <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Cola</th>
                      <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Fecha</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recent.map((c, i) => (
                      <tr key={c.id} style={{ borderTop: '1px solid #EFF4F7', background: i % 2 === 1 ? '#FAFBFC' : '#fff' }}>
                        <td className="px-4 py-3 fw-semibold" style={{ color: c.criticality >= 7 ? '#B22F2F' : '#123B5D' }}>
                          {c.criticality.toFixed(1)}
                        </td>
                        <td className="px-4 py-3 text-uppercase" style={{ fontSize: 12 }}>{c.priority}</td>
                        <td className="px-4 py-3" style={{ fontSize: 12 }}>{c.queue}</td>
                        <td className="px-4 py-3 text-muted font-monospace" style={{ fontSize: 12 }}>{formatTs(c.timestamp)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </Col>

        {/* Pie */}
        <Col xs={12} lg={5}>
          <Card className="cc-card">
            <div className="cc-card-header">Proporción por prioridad</div>
            <Card.Body>
              {data.status === 'loading' ? (
                <div className="small text-muted">Cargando…</div>
              ) : data.status === 'error' ? (
                <div className="small" style={{ color: '#B22F2F' }}>Sin datos disponibles.</div>
              ) : total === 0 ? (
                <div className="small text-muted">Sin lecturas clasificadas.</div>
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie
                      data={rows.map(r => ({ name: `${r.priority} → ${r.queue}`, value: r.count }))}
                      cx="50%" cy="50%" outerRadius={90}
                      dataKey="value"
                      label={({ percent }) => `${(percent * 100).toFixed(0)}%`}
                      labelLine={false}
                      isAnimationActive={false}
                    >
                      {rows.map((r, i) => <Cell key={`qm-cell-${i}`} fill={r.color} />)}
                    </Pie>
                    <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => [`${v} lecturas`]} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Análisis histórico de criticidad (TSK-052, muestra acotada) */}
      <Row className="g-4 mt-1">
        <Col xs={12} lg={7}>
          <Card className="cc-card">
            <div className="cc-card-header">Evolución de criticidad (muestra)</div>
            <Card.Body>
              {hist.classStatus === 'loading' ? (
                <div className="small text-muted">Cargando…</div>
              ) : hist.classStatus === 'error' ? (
                <div className="small" style={{ color: '#B22F2F' }}>
                  No se pudo cargar. <button onClick={hist.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
                </div>
              ) : critEvolution.length === 0 ? (
                <div className="small text-muted">Sin clasificaciones en el periodo.</div>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={critEvolution} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" />
                    <XAxis dataKey="t" tick={TICK_STYLE} interval="preserveStartEnd" minTickGap={48} />
                    <YAxis tick={TICK_STYLE} domain={[3, 9]} />
                    <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => `${Number(v).toFixed(1)}`} />
                    <Line type="monotone" dataKey="criticality" name="Criticidad" stroke="#C83B3B" strokeWidth={2} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              )}
              <p className="text-muted mt-2 mb-0" style={{ fontSize: 11 }}>
                Muestra de {hist.classSampleCount} clasificaciones recientes, no el total global.
              </p>
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} lg={5}>
          <Card className="cc-card h-100">
            <div className="cc-card-header">Distribución de criticidad (muestra)</div>
            <Card.Body>
              {hist.classStatus === 'loading' ? (
                <div className="small text-muted">Cargando…</div>
              ) : hist.classStatus === 'error' ? (
                <div className="small" style={{ color: '#B22F2F' }}>No se pudo cargar.</div>
              ) : (
                <>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={hist.criticalityBuckets} margin={{ top: 4, right: 8, left: 0, bottom: 4 }} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" horizontal={false} />
                      <XAxis type="number" tick={TICK_STYLE} allowDecimals={false} />
                      <YAxis type="category" dataKey="range" tick={TICK_STYLE} width={90} />
                      <Tooltip contentStyle={TOOLTIP_STYLE} />
                      <Bar dataKey="count" name="Clasificaciones" radius={[0, 3, 3, 0]} isAnimationActive={false}>
                        {hist.criticalityBuckets.map((e, i) => <Cell key={`tcb-cell-${i}`} fill={e.color} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                  <p className="text-muted mt-2 mb-0" style={{ fontSize: 11 }}>
                    Muestra de {hist.classSampleCount} clasificaciones recientes, no el total global.
                  </p>
                </>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
