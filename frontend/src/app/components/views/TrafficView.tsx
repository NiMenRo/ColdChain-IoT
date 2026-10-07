import { AreaChart, Area, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie } from 'recharts';
import { Info } from 'lucide-react';
import { Card, Row, Col } from '../../lib/bootstrap';

// ─── Static classification mapping (backend-defined, not user-configurable) ──
const QUEUE_MAPPING = [
  {
    priority: 'HIGH',   queue: 'WFQ',         description: 'Alertas críticas y lecturas fuera de rango. Procesamiento prioritario garantizado.',
    color: '#C83B3B',   bg: '#FCEEEE',         border: '#f1aeb5',
    count: 38,  pct: 9.3,
  },
  {
    priority: 'MEDIUM', queue: 'Round Robin',  description: 'Telemetría periódica estándar. Distribución equitativa entre dispositivos.',
    color: '#C47A00',   bg: '#FFF5E3',         border: '#ffda6a',
    count: 127, pct: 31.1,
  },
  {
    priority: 'LOW',    queue: 'FIFO',         description: 'Datos de diagnóstico, logs y lecturas de baja frecuencia.',
    color: '#16835B',   bg: '#EAF6EF',         border: '#a3cfbb',
    count: 241, pct: 59.0,
    // Note: 9.3 + 31.1 + 59.6 ≈ 100 (rounded to 59.0 for display)
  },
];

const TOTAL_READINGS = QUEUE_MAPPING.reduce((s, r) => s + r.count, 0);

// ─── Deterministic time-series data ──────────────────────────────────────────
const timeSeriesData = [
  { t: '00:00', high: 3,  medium: 12, low: 22 },
  { t: '01:00', high: 2,  medium: 10, low: 20 },
  { t: '02:00', high: 1,  medium:  8, low: 18 },
  { t: '03:00', high: 1,  medium:  7, low: 16 },
  { t: '04:00', high: 2,  medium:  9, low: 19 },
  { t: '05:00', high: 2,  medium: 10, low: 21 },
  { t: '06:00', high: 3,  medium: 12, low: 24 },
  { t: '07:00', high: 4,  medium: 15, low: 28 },
  { t: '08:00', high: 6,  medium: 18, low: 32 },
  { t: '09:00', high: 8,  medium: 22, low: 38 },
  { t: '10:00', high: 9,  medium: 24, low: 41 },
  { t: '11:00', high: 7,  medium: 21, low: 39 },
  { t: '12:00', high: 5,  medium: 18, low: 35 },
];

const CHART_MARGIN = { top: 4, right: 8, left: 0, bottom: 4 };
const TICK_STYLE   = { fill: '#52616B', fontSize: 11 };
const TOOLTIP_STYLE = { border: '1px solid #D9E2E8', borderRadius: '4px', fontSize: '12px' };

export function TrafficView() {
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

      {/* Summary KPIs */}
      <Row className="g-3 mb-4">
        {QUEUE_MAPPING.map(row => (
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
                <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Lecturas (mock)</th>
                <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Descripción</th>
              </tr>
            </thead>
            <tbody>
              {QUEUE_MAPPING.map((row, i) => (
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
                      <span className="fw-semibold" style={{ color: row.color }}>{row.count}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-muted" style={{ fontSize: 12 }}>{row.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 py-2 border-top small text-muted">
            Total: {TOTAL_READINGS} lecturas clasificadas en el periodo actual.
          </div>
        </div>
      </Card>

      <Row className="g-4">
        {/* Time series */}
        <Col xs={12} lg={7}>
          <Card className="cc-card">
            <div className="cc-card-header">Distribución temporal de lecturas por prioridad</div>
            <Card.Body>
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={timeSeriesData} margin={CHART_MARGIN}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" />
                  <XAxis dataKey="t" tick={TICK_STYLE} />
                  <YAxis tick={TICK_STYLE} label={{ value: 'lecturas', angle: -90, position: 'insideLeft', fill: '#52616B', fontSize: 11 }} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Area type="monotone" dataKey="high"   stackId="1" name="HIGH"   stroke="#C83B3B" fill="#C83B3B" fillOpacity={0.7} isAnimationActive={false} />
                  <Area type="monotone" dataKey="medium" stackId="1" name="MEDIUM" stroke="#C47A00" fill="#C47A00" fillOpacity={0.7} isAnimationActive={false} />
                  <Area type="monotone" dataKey="low"    stackId="1" name="LOW"    stroke="#16835B" fill="#16835B" fillOpacity={0.7} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </Card.Body>
          </Card>
        </Col>

        {/* Pie */}
        <Col xs={12} lg={5}>
          <Card className="cc-card">
            <div className="cc-card-header">Proporción por prioridad</div>
            <Card.Body>
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={QUEUE_MAPPING.map(r => ({ name: `${r.priority} → ${r.queue}`, value: r.count }))}
                    cx="50%" cy="50%" outerRadius={90}
                    dataKey="value"
                    label={({ percent }) => `${(percent * 100).toFixed(0)}%`}
                    labelLine={false}
                    isAnimationActive={false}
                  >
                    {QUEUE_MAPPING.map((r, i) => <Cell key={`qm-cell-${i}`} fill={r.color} />)}
                  </Pie>
                  <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => [`${v} lecturas`]} />
                </PieChart>
              </ResponsiveContainer>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
