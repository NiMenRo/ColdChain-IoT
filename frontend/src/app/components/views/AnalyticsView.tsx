import { useMemo, useState } from 'react';
import { LineChart, Line, BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie } from 'recharts';
import { Activity, TrendingDown, TrendingUp, Wifi } from 'lucide-react';
import { Card, Row, Col } from '../../lib/bootstrap';
import { useExperiments } from '../../contexts/ExperimentContext';
import {
  ExperimentRun,
  COUNTER_METRICS,
  LATENCY_METRICS,
  METRIC_LABELS,
  METRIC_UNITS,
  SENSOR_CONDITION_LABELS,
  SensorCondition,
} from '../../types/experiments';
import {
  sumMetric,
  avgMetric,
  maxMetric,
  seriesByElapsed,
  mergeLineSeries,
} from '../../lib/experimentAggregations';
import {
  ScenarioBadge,
  MetricComparisonCard,
  LineComparisonChart,
  BacklogChart,
  CountMetricsBarChart,
} from '../experiments/ExperimentCharts';

// ─── Mock histórico complementario (NO asociado a run_id) ───
const HOURS = ['00:00','01:00','02:00','03:00','04:00','05:00','06:00','07:00','08:00','09:00','10:00','11:00','12:00','13:00','14:00','15:00','16:00','17:00','18:00','19:00','20:00','21:00','22:00','23:00'];

const latencyData = [42,44,41,40,38,37,39,43,47,52,55,51,48,46,50,53,49,47,46,44,43,45,44,42].map((v, i) => ({ hour: HOURS[i], latency: v }));
const jitterData  = [2.1,2.3,2.0,1.9,1.8,1.7,1.9,2.2,2.8,3.4,3.7,3.2,2.9,2.7,3.1,3.5,3.0,2.8,2.7,2.5,2.4,2.6,2.5,2.2].map((v, i) => ({ hour: HOURS[i], jitter: v }));
const lossData    = [0.6,0.7,0.6,0.5,0.5,0.4,0.5,0.7,0.8,1.0,1.1,0.9,0.8,0.8,0.9,1.1,0.9,0.8,0.8,0.7,0.7,0.8,0.7,0.6].map((v, i) => ({ hour: HOURS[i], loss: v }));
const pdrData     = [99.4,99.3,99.4,99.5,99.5,99.6,99.5,99.3,99.2,99.0,98.9,99.1,99.2,99.2,99.1,98.9,99.1,99.2,99.2,99.3,99.3,99.2,99.3,99.4].map((v, i) => ({ hour: HOURS[i], pdr: v }));

const alertsByType = [
  { name: 'Temp. Excedida',    value: 12, color: '#C83B3B' },
  { name: 'Temp. Bajo Mín.',   value: 4,  color: '#1F6F8B' },
  { name: 'Humedad > Máx.',    value: 7,  color: '#965D00' },
  { name: 'Humedad < Mín.',    value: 3,  color: '#27B3C2' },
  { name: 'Anomalía Energía',  value: 5,  color: '#52616B' },
];

const priorityDist = [
  { name: 'HIGH',   value: 38,  color: '#C83B3B' },
  { name: 'MEDIUM', value: 127, color: '#C47A00' },
  { name: 'LOW',    value: 241, color: '#16835B' },
];

const queueDist = [
  { name: 'WFQ',         value: 38,  color: '#C83B3B' },
  { name: 'Round Robin', value: 127, color: '#C47A00' },
  { name: 'FIFO',        value: 241, color: '#16835B' },
];

const CHART_MARGIN = { top: 4, right: 8, left: 0, bottom: 4 };
const TICK_STYLE   = { fill: '#52616B', fontSize: 11 };
const TOOLTIP_STYLE = { border: '1px solid #D9E2E8', borderRadius: '4px', fontSize: '12px' };
const LEGEND_STYLE  = { wrapperStyle: { fontSize: '12px' } };

function runNumber(runs: ExperimentRun[], run: ExperimentRun): number {
  const sorted = [...runs].sort((a, b) => a.started_at.localeCompare(b.started_at));
  return sorted.findIndex(r => r.id === run.id) + 1;
}

function runLabel(runs: ExperimentRun[], run: ExperimentRun, condition: SensorCondition): string {
  return `${SENSOR_CONDITION_LABELS[condition]} — ${run.scenario === 'WITH_QOS' ? 'Con priorización' : 'Sin priorización'} — Ejecución #${runNumber(runs, run)}`;
}

export function AnalyticsView() {
  const { runs, metrics, runMeta } = useExperiments();
  const [condition, setCondition] = useState<SensorCondition>('normal');
  const [withQosId, setWithQosId] = useState<string | null>(null);
  const [withoutQosId, setWithoutQosId] = useState<string | null>(null);

  const runsInCondition = useMemo(
    () => runs.filter(r => runMeta[r.id]?.sensorCondition === condition),
    [runs, runMeta, condition],
  );
  const withQosRuns = runsInCondition.filter(r => r.scenario === 'WITH_QOS');
  const withoutQosRuns = runsInCondition.filter(r => r.scenario === 'WITHOUT_QOS');

  const withQosRun = withQosRuns.find(r => r.id === withQosId)
    ?? [...withQosRuns].sort((a, b) => b.started_at.localeCompare(a.started_at))[0]
    ?? null;
  const withoutQosRun = withoutQosRuns.find(r => r.id === withoutQosId)
    ?? [...withoutQosRuns].sort((a, b) => b.started_at.localeCompare(a.started_at))[0]
    ?? null;

  const withQosMetrics = withQosRun ? metrics.filter(m => m.run_id === withQosRun.id) : [];
  const withoutQosMetrics = withoutQosRun ? metrics.filter(m => m.run_id === withoutQosRun.id) : [];

  const persistData = mergeLineSeries(
    withQosRun ? seriesByElapsed(metrics, 'ingest_to_persist_ms', withQosRun.started_at) : [],
    withoutQosRun ? seriesByElapsed(metrics, 'ingest_to_persist_ms', withoutQosRun.started_at) : [],
  );
  const alertData = mergeLineSeries(
    withQosRun ? seriesByElapsed(metrics, 'ingest_to_alert_ms', withQosRun.started_at) : [],
    withoutQosRun ? seriesByElapsed(metrics, 'ingest_to_alert_ms', withoutQosRun.started_at) : [],
  );

  const totalPriority = priorityDist.reduce((s, d) => s + d.value, 0);
  const totalQueue    = queueDist.reduce((s, d) => s + d.value, 0);

  const kpis = [
    { label: 'Latencia media',     value: '47 ms',   sub: 'Últimas 24 h',    good: true,  Icon: TrendingDown },
    { label: 'Jitter',             value: '3.2 ms',  sub: 'Últimas 24 h',    good: true,  Icon: Activity     },
    { label: 'Pérdida de paquetes',value: '0.8 %',   sub: 'Últimas 24 h',    good: true,  Icon: TrendingDown },
    { label: 'PDR',                value: '99.2 %',  sub: 'Tasa de entrega', good: true,  Icon: TrendingUp   },
    { label: 'Throughput',         value: '95 Mbps', sub: 'Promedio',        good: true,  Icon: TrendingUp   },
    { label: 'Alertas generadas',  value: '31',      sub: 'Últimos 7 días',  good: false, Icon: Wifi         },
  ];

  return (
    <div>
      <h1 className="mb-1" style={{ fontSize: 20, fontWeight: 600 }}>QoS — Análisis de Rendimiento</h1>
      <p className="text-muted small mb-4">
        Análisis de las ejecuciones registradas (ExperimentRun) y analítica QoS complementaria histórica.
      </p>

      {/* ─── Comparación experimental ─── */}
      <h2 className="small fw-semibold text-muted text-uppercase mb-3" style={{ letterSpacing: '0.06em' }}>
        Comparación experimental
      </h2>

      <Card className="cc-card mb-4">
        <Card.Body>
          <div className="mb-4">
            <div className="small fw-semibold text-muted mb-2">Condición de sensores</div>
            <div className="d-flex gap-2">
              {(['normal', 'altered'] as const).map(c => (
                <button key={c} type="button"
                  className="btn btn-sm"
                  style={{
                    border: `1px solid ${condition === c ? '#123B5D' : '#D9E2E8'}`,
                    background: condition === c ? '#F5F8FA' : '#fff',
                    fontWeight: condition === c ? 600 : 400,
                  }}
                  onClick={() => { setCondition(c); setWithQosId(null); setWithoutQosId(null); }}>
                  {SENSOR_CONDITION_LABELS[c]}
                </button>
              ))}
            </div>
          </div>

          <Row className="g-3 mb-2 align-items-end">
            <Col xs={12} md={6}>
              <label className="small fw-semibold text-muted d-block mb-1">Ejecución con priorización</label>
              <select className="form-select form-select-sm" value={withQosRun?.id ?? ''}
                onChange={e => setWithQosId(e.target.value || null)}>
                {withQosRuns.length === 0 && <option value="">Sin ejecuciones</option>}
                {withQosRuns.map(r => (
                  <option key={r.id} value={r.id}>{runLabel(runs, r, condition)}</option>
                ))}
              </select>
            </Col>
            <Col xs={12} md={6}>
              <label className="small fw-semibold text-muted d-block mb-1">Ejecución sin priorización</label>
              <select className="form-select form-select-sm" value={withoutQosRun?.id ?? ''}
                onChange={e => setWithoutQosId(e.target.value || null)}>
                {withoutQosRuns.length === 0 && <option value="">Sin ejecuciones</option>}
                {withoutQosRuns.map(r => (
                  <option key={r.id} value={r.id}>{runLabel(runs, r, condition)}</option>
                ))}
              </select>
            </Col>
          </Row>

          <p className="small text-muted mb-0">
            Condición: <strong>{SENSOR_CONDITION_LABELS[condition]}</strong> · comparación
            {' '}<strong>Con priorización</strong> vs <strong>Sin priorización</strong>.
          </p>
        </Card.Body>
      </Card>

      {withQosRun && withoutQosRun ? (
        <>
          <div className="mb-4">
            <h3 className="mb-3" style={{ fontSize: 14, fontWeight: 600 }}>Resumen comparativo</h3>
            <Row className="g-3">
              {COUNTER_METRICS.map(type => (
                <Col key={type} xs={12} sm={6} xl={3}>
                  <MetricComparisonCard
                    label={METRIC_LABELS[type]}
                    unit={METRIC_UNITS[type]}
                    withQosValue={sumMetric(withQosMetrics, type)}
                    withoutQosValue={sumMetric(withoutQosMetrics, type)}
                    higherIsBetter={type === 'readings_persisted' || type === 'messages_received'}
                  />
                </Col>
              ))}
            </Row>
          </div>

          <div className="mb-4">
            <h3 className="mb-3" style={{ fontSize: 14, fontWeight: 600 }}>Latencias</h3>
            <Row className="g-3 mb-4">
              {LATENCY_METRICS.map(type => (
                <Col key={type} xs={12} sm={6}>
                  <div className="p-3 rounded-3" style={{ background: '#fff', border: '1px solid #D9E2E8' }}>
                    <div className="small fw-semibold text-muted mb-3">{METRIC_LABELS[type]}</div>
                    <div className="d-flex justify-content-between mb-2">
                      <span className="small">Con priorización</span>
                      <span className="fw-bold">
                        {avgMetric(withQosMetrics, type) !== null ? `${avgMetric(withQosMetrics, type)!.toFixed(1)} ms` : '—'}
                        <span className="text-muted small fw-normal"> avg</span>
                        {' · '}
                        {maxMetric(withQosMetrics, type) !== null ? `${maxMetric(withQosMetrics, type)} ms` : '—'}
                        <span className="text-muted small fw-normal"> máx</span>
                      </span>
                    </div>
                    <div className="d-flex justify-content-between">
                      <span className="small">Sin priorización</span>
                      <span className="fw-bold">
                        {avgMetric(withoutQosMetrics, type) !== null ? `${avgMetric(withoutQosMetrics, type)!.toFixed(1)} ms` : '—'}
                        <span className="text-muted small fw-normal"> avg</span>
                        {' · '}
                        {maxMetric(withoutQosMetrics, type) !== null ? `${maxMetric(withoutQosMetrics, type)} ms` : '—'}
                        <span className="text-muted small fw-normal"> máx</span>
                      </span>
                    </div>
                  </div>
                </Col>
              ))}
            </Row>

            <Row className="g-4 mb-4">
              <Col xs={12} lg={6}>
                <LineComparisonChart title="Latencia de persistencia" data={persistData} />
              </Col>
              <Col xs={12} lg={6}>
                <LineComparisonChart title="Latencia hasta alerta" data={alertData} />
              </Col>
            </Row>

            <BacklogChart withQosRun={withQosRun} withoutQosRun={withoutQosRun} allMetrics={metrics} />
          </div>

          <CountMetricsBarChart withQosRun={withQosRun} withoutQosRun={withoutQosRun} allMetrics={metrics} />

          <p className="small text-muted mt-3 mb-0">
            Nota: Sin priorización no utiliza clasificación, colas FIFO/RR/WFQ ni métricas QoS; las diferencias reflejan el impacto de la priorización en el procesamiento.
          </p>
        </>
      ) : (
        <div className="p-4 rounded-3 mb-4 text-center text-muted small" style={{ background: '#F5F8FA', border: '1px dashed #D9E2E8' }}>
          No hay suficientes ejecuciones para comparar bajo la condición <strong>{SENSOR_CONDITION_LABELS[condition]}</strong>.
          Ejecuta simulaciones desde la pantalla de Simulación.
        </div>
      )}

      {/* ─── Analítica QoS complementaria (histórica, con priorización) ─── */}
      <hr className="my-5" style={{ borderColor: '#D9E2E8' }} />
      <h2 className="mb-1" style={{ fontSize: 16, fontWeight: 600 }}>
        Analítica QoS complementaria
      </h2>
      <p className="text-muted small mb-4">
        Histórica · Solo disponible para ejecuciones con priorización.
      </p>

      <Row className="g-3 mb-4">
        {kpis.map(m => {
          const Icon = m.Icon;
          const col  = m.good ? '#52616B' : '#C83B3B';
          return (
            <Col key={m.label} xs={12} sm={6} xl={4}>
              <div className="cc-card p-3">
                <div className="d-flex justify-content-between align-items-start mb-1">
                  <div className="small text-muted">{m.label}</div>
                  <Icon size={16} color={col} />
                </div>
                <div style={{ fontSize: 22, fontWeight: 700, margin: '6px 0 4px' }}>{m.value}</div>
                <div className="small text-muted">{m.sub}</div>
              </div>
            </Col>
          );
        })}
      </Row>

      <Card className="cc-card mb-4">
        <div className="cc-card-header">Latencia (ms) — últimas 24 h</div>
        <Card.Body>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={latencyData} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" />
              <XAxis dataKey="hour" tick={TICK_STYLE} interval={3} />
              <YAxis tick={TICK_STYLE} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Line type="monotone" dataKey="latency" name="Latencia" stroke="#123B5D" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card.Body>
      </Card>

      <Row className="g-4 mb-4">
        <Col xs={12} lg={6}>
          <Card className="cc-card">
            <div className="cc-card-header">Jitter (ms) — últimas 24 h</div>
            <Card.Body>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={jitterData} margin={CHART_MARGIN}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" />
                  <XAxis dataKey="hour" tick={TICK_STYLE} interval={5} />
                  <YAxis tick={TICK_STYLE} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Line type="monotone" dataKey="jitter" name="Jitter" stroke="#1F6F8B" strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card className="cc-card">
            <div className="cc-card-header">Pérdida de paquetes (%) — últimas 24 h</div>
            <Card.Body>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={lossData} margin={CHART_MARGIN}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" />
                  <XAxis dataKey="hour" tick={TICK_STYLE} interval={5} />
                  <YAxis tick={TICK_STYLE} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Line type="monotone" dataKey="loss" name="Pérdida %" stroke="#C83B3B" strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Card className="cc-card mb-4">
        <div className="cc-card-header">PDR — Tasa de entrega de paquetes (%) — últimas 24 h</div>
        <Card.Body>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={pdrData} margin={CHART_MARGIN}>
              <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" />
              <XAxis dataKey="hour" tick={TICK_STYLE} interval={3} />
              <YAxis tick={TICK_STYLE} domain={[98, 100]} />
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => `${v.toFixed(1)}%`} />
              <Line type="monotone" dataKey="pdr" name="PDR" stroke="#16835B" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card.Body>
      </Card>

      <Row className="g-4">
        <Col xs={12} lg={4}>
          <Card className="cc-card h-100">
            <div className="cc-card-header">Alertas por tipo (últimos 7 días)</div>
            <Card.Body>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={alertsByType} cx="50%" cy="50%" outerRadius={75} dataKey="value" isAnimationActive={false}>
                    {alertsByType.map((e, i) => <Cell key={`at-cell-${i}`} fill={e.color} />)}
                  </Pie>
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Legend {...LEGEND_STYLE} />
                </PieChart>
              </ResponsiveContainer>
            </Card.Body>
          </Card>
        </Col>

        <Col xs={12} lg={4}>
          <Card className="cc-card h-100">
            <div className="cc-card-header">Distribución por prioridad</div>
            <Card.Body>
              <div className="d-flex flex-column gap-3 pt-2">
                {priorityDist.map(p => {
                  const pct = Math.round((p.value / totalPriority) * 100);
                  return (
                    <div key={p.name}>
                      <div className="d-flex justify-content-between mb-1">
                        <span className="fw-semibold" style={{ fontSize: 13 }}>{p.name}</span>
                        <span className="text-muted small">{p.value} ({pct}%)</span>
                      </div>
                      <div style={{ height: 10, background: '#EFF4F7', borderRadius: 5 }}>
                        <div style={{ height: '100%', width: `${pct}%`, background: p.color, borderRadius: 5 }} />
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className="text-muted mt-4 mb-0" style={{ fontSize: 11 }}>
                Total: {totalPriority} lecturas clasificadas
              </p>
            </Card.Body>
          </Card>
        </Col>

        <Col xs={12} lg={4}>
          <Card className="cc-card h-100">
            <div className="cc-card-header">Distribución por cola</div>
            <Card.Body>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={queueDist} margin={CHART_MARGIN} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" horizontal={false} />
                  <XAxis type="number" tick={TICK_STYLE} />
                  <YAxis type="category" dataKey="name" tick={TICK_STYLE} width={90} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Bar dataKey="value" name="Lecturas" radius={[0, 3, 3, 0]} isAnimationActive={false}>
                    {queueDist.map((e, i) => <Cell key={`qd-cell-${i}`} fill={e.color} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p className="text-muted mt-2 mb-0" style={{ fontSize: 11 }}>
                Total: {totalQueue} lecturas clasificadas
              </p>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
