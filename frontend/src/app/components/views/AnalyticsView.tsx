import { useMemo, useState } from 'react';
import { LineChart, Line, BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie } from 'recharts';
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
import { useQosSnapshot } from '../../hooks/useQosSnapshot';
import type { HistorySummary, QosTrendPoint } from '../../../services/api/history';
import { RANGE_OPTIONS, useHistoricalAnalytics, type HistoryRange } from '../../hooks/useHistoricalAnalytics';
import { alertLabel, formatTs } from '../../hooks/useAlertsData';
import {
  ScenarioBadge,
  MetricComparisonCard,
  LineComparisonChart,
  BacklogChart,
  CountMetricsBarChart,
} from '../experiments/ExperimentCharts';

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

// ─── Helpers de presentación histórica (TSK-052; solo formato, sin agregación) ─

function bucketLabel(bucket: string, range: string): string {
  const d = new Date(bucket);
  if (Number.isNaN(d.getTime())) return bucket;
  const hhmm = d.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' });
  if (range === '30d') {
    return d.toLocaleDateString('es-CO', { day: '2-digit', month: '2-digit' });
  }
  return `${d.toLocaleDateString('es-CO', { day: '2-digit', month: '2-digit' })} ${hhmm}`;
}

type QosMetricKey = 'latency' | 'jitter' | 'packet_loss' | 'throughput' | 'pdr';

const QOS_METRIC_OPTIONS: Array<{ key: QosMetricKey; label: string; unit: string }> = [
  { key: 'latency', label: 'Latencia', unit: 'ms' },
  { key: 'jitter', label: 'Jitter', unit: 'ms' },
  { key: 'packet_loss', label: 'Pérdida', unit: '%' },
  { key: 'throughput', label: 'Throughput', unit: '' },
  { key: 'pdr', label: 'PDR', unit: '%' },
];

function qosLabel(key: QosMetricKey): string {
  return QOS_METRIC_OPTIONS.find(o => o.key === key)?.label ?? key;
}

function qosValue(p: QosTrendPoint, key: QosMetricKey): number {
  if (key === 'latency') return p.avg_latency;
  if (key === 'jitter') return p.avg_jitter;
  if (key === 'packet_loss') return p.avg_packet_loss;
  if (key === 'throughput') return p.avg_throughput;
  return p.avg_pdr;
}

function qosFormat(key: QosMetricKey, v: number): string {
  const unit = QOS_METRIC_OPTIONS.find(o => o.key === key)?.unit ?? '';
  return `${v.toFixed(1)}${unit ? ` ${unit}` : ''}`;
}

const ALERT_TYPE_COLORS: Record<string, string> = {
  TEMPERATURE_EXCEEDED: '#C83B3B',
  TEMPERATURE_BELOW_MIN: '#1F6F8B',
  HUMIDITY_ABOVE_MAX: '#965D00',
  HUMIDITY_BELOW_MIN: '#27B3C2',
  ENERGY_STATE_ANOMALY: '#52616B',
};

function alertTypeEntries(summary: HistorySummary | null): Array<{ name: string; value: number; color: string }> {
  if (!summary) return [];
  return Object.entries(summary.alerts_by_type ?? {}).map(([type, value]) => ({
    name: alertLabel(type),
    value,
    color: ALERT_TYPE_COLORS[type] ?? '#8A9BA8',
  }));
}

const PRIORITY_META: Array<{ key: string; name: string; color: string }> = [
  { key: 'high', name: 'HIGH', color: '#C83B3B' },
  { key: 'medium', name: 'MEDIUM', color: '#C47A00' },
  { key: 'low', name: 'LOW', color: '#16835B' },
];

const QUEUE_COLORS: Record<string, string> = {
  WFQ: '#C83B3B',
  'Round Robin': '#C47A00',
  FIFO: '#16835B',
};

function priorityEntries(summary: HistorySummary | null): Array<{ name: string; value: number; pct: number; color: string }> {
  const t = summary?.traffic_by_priority ?? {};
  const rows = PRIORITY_META.map(m => ({
    name: m.name,
    value: typeof t[m.key] === 'number' ? t[m.key] : 0,
    pct: 0,
    color: m.color,
  }));
  const total = rows.reduce((s, r) => s + r.value, 0);
  return rows.map(r => ({ ...r, pct: total > 0 ? Math.round((r.value / total) * 100) : 0 }));
}

function queueEntries(summary: HistorySummary | null): Array<{ name: string; value: number; color: string }> {
  const q = summary?.qos_by_queue ?? {};
  return Object.entries(q).map(([name, value]) => ({
    name,
    value,
    color: QUEUE_COLORS[name] ?? '#8A9BA8',
  }));
}

function summaryIndicators(summary: HistorySummary): Array<{ label: string; value: string; sub: string }> {
  const byType = Object.entries(summary.alerts_by_type ?? {});
  const topType = byType.length > 0 ? byType.reduce((a, b) => (b[1] > a[1] ? b : a)) : null;
  const byPrio = summary.traffic_by_priority ?? {};
  const prioTotal = ['high', 'medium', 'low'].reduce((s, k) => s + (typeof byPrio[k] === 'number' ? byPrio[k] : 0), 0);
  const highPct = prioTotal > 0 && typeof byPrio.high === 'number' ? Math.round((byPrio.high / prioTotal) * 100) : 0;
  return [
    { label: 'Lecturas registradas', value: String(summary.total_readings), sub: 'Acumulado backend' },
    { label: 'Clasificaciones', value: String(summary.total_classifications), sub: 'Acumulado backend' },
    { label: 'Métricas QoS', value: String(summary.total_qos_metrics), sub: 'Acumulado backend' },
    {
      label: 'Tipo de alerta predominante',
      value: topType ? alertLabel(topType[0]) : '—',
      sub: topType ? `${topType[1]} alertas · ${highPct}% del tráfico es HIGH` : 'Sin alertas registradas',
    },
  ];
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
  const qosLive = useQosSnapshot();
  const hist = useHistoricalAnalytics();
  const [qosMetric, setQosMetric] = useState<QosMetricKey>('latency');

  const persistData = mergeLineSeries(
    withQosRun ? seriesByElapsed(metrics, 'ingest_to_persist_ms', withQosRun.started_at) : [],
    withoutQosRun ? seriesByElapsed(metrics, 'ingest_to_persist_ms', withoutQosRun.started_at) : [],
  );
  const alertData = mergeLineSeries(
    withQosRun ? seriesByElapsed(metrics, 'ingest_to_alert_ms', withQosRun.started_at) : [],
    withoutQosRun ? seriesByElapsed(metrics, 'ingest_to_alert_ms', withoutQosRun.started_at) : [],
  );

  return (
    <div>
      <h1 className="mb-1" style={{ fontSize: 20, fontWeight: 600 }}>QoS — Análisis de Rendimiento</h1>
      <p className="text-muted small mb-4">
        Análisis de las ejecuciones registradas (ExperimentRun) y analítica QoS complementaria histórica.
      </p>

      {/* ─── Estado actual QoS — datos en vivo (TSK-050; análisis histórico → TSK-052) ─── */}
      <h2 className="small fw-semibold text-muted text-uppercase mb-3" style={{ letterSpacing: '0.06em' }}>
        Estado actual QoS
      </h2>

      {(qosLive.isAuthBlocked || qosLive.isConfigMissing) && !qosLive.isLoading && (
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-3 rounded-3 px-4 py-3 mb-4"
          style={{ background: '#FFF5E3', border: '1px solid #ffda6a', borderLeft: '4px solid #C47A00' }}>
          <p className="mb-0 small">
            <strong>Datos en vivo no disponibles.</strong>{' '}
            {qosLive.isConfigMissing
              ? 'Falta configurar VITE_API_BASE_URL en el frontend.'
              : 'La API requiere autenticación Bearer. Inicie sesión nuevamente si su sesión expiró.'}
          </p>
          <button
            onClick={qosLive.retry}
            className="border-0 bg-transparent fw-semibold"
            style={{ fontSize: 13, color: '#965D00', cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            Reintentar
          </button>
        </div>
      )}

      <Row className="g-3 mb-4">
        {qosLive.status === 'loading' ? (
          <div className="text-muted small px-3 py-4">Cargando métricas QoS…</div>
        ) : qosLive.status === 'error' ? (
          <div className="px-3 py-4 small" style={{ color: '#B22F2F' }}>
            No se pudieron cargar las métricas QoS. <button onClick={qosLive.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
          </div>
        ) : qosLive.cells.length === 0 ? (
          <div className="text-muted small px-3 py-4">Sin métricas QoS disponibles en la sesión actual.</div>
        ) : (
          qosLive.cells.map(m => (
            <Col key={m.label} xs={12} sm={6} xl={4}>
              <div className="cc-card p-3">
                <div className="small text-muted">{m.label}</div>
                <div style={{ fontSize: 22, fontWeight: 700, margin: '6px 0 4px' }}>{m.value}</div>
                <div className="small text-muted">{m.sub}</div>
              </div>
            </Col>
          ))
        )}
      </Row>

      <Card className="cc-card mb-4">
        <div className="cc-card-header">Registros QoS recientes</div>
        {qosLive.recentStatus === 'loading' ? (
          <div className="p-4 small text-muted">Cargando registros…</div>
        ) : qosLive.recentStatus === 'error' ? (
          <div className="p-4 small" style={{ color: '#B22F2F' }}>
            No se pudieron cargar los registros. <button onClick={qosLive.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
          </div>
        ) : qosLive.recent.length === 0 ? (
          <div className="p-4 small text-muted">Sin registros QoS persistidos.</div>
        ) : (
          <div className="overflow-hidden">
            <table className="w-100" style={{ borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#F5F8FA' }}>
                  <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Latencia (ms)</th>
                  <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Jitter (ms)</th>
                  <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Pérdida (%)</th>
                  <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>PDR (%)</th>
                  <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Throughput</th>
                  <th className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>Fecha</th>
                </tr>
              </thead>
              <tbody>
                {qosLive.recent.map((r, i) => (
                  <tr key={r.id} style={{ borderTop: '1px solid #EFF4F7', background: i % 2 === 1 ? '#FAFBFC' : '#fff' }}>
                    <td className="px-4 py-3">{r.latency.toFixed(0)}</td>
                    <td className="px-4 py-3">{r.jitter.toFixed(1)}</td>
                    <td className="px-4 py-3">{r.packet_loss.toFixed(1)}</td>
                    <td className="px-4 py-3">{r.pdr.toFixed(1)}</td>
                    <td className="px-4 py-3">{r.throughput.toFixed(1)}</td>
                    <td className="px-4 py-3 text-muted font-monospace" style={{ fontSize: 12 }}>{formatTs(r.timestamp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

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

      {/* ─── Análisis histórico — datos reales (TSK-052) ─── */}
      <hr className="my-5" style={{ borderColor: '#D9E2E8' }} />
      <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-1">
        <h2 className="mb-0" style={{ fontSize: 16, fontWeight: 600 }}>
          Análisis histórico
        </h2>
        <div className="d-flex align-items-center gap-2 flex-wrap">
          <span className="small fw-semibold text-muted">Periodo:</span>
          {RANGE_OPTIONS.map(o => (
            <button key={o.value} type="button" onClick={() => hist.setRange(o.value)}
              className="rounded-2 border px-3 py-1"
              style={{ fontSize: 12, cursor: 'pointer', fontWeight: hist.range === o.value ? 600 : 400,
                background: hist.range === o.value ? '#123B5D' : '#fff',
                color: hist.range === o.value ? '#fff' : '#52616B',
                borderColor: hist.range === o.value ? '#123B5D' : '#D9E2E8' }}>
              {o.label}
            </button>
          ))}
        </div>
      </div>
      <p className="text-muted small mb-4">
        Agregados del backend (`/history/*`) para {hist.rangeLabel.toLowerCase()}. Las distribuciones por
        criticidad y por día usan una muestra paginada acotada (máx. 100 registros), no el total global.
      </p>

      {(hist.isAuthBlocked || hist.isConfigMissing) && !hist.isLoading && (
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-3 rounded-3 px-4 py-3 mb-4"
          style={{ background: '#FFF5E3', border: '1px solid #ffda6a', borderLeft: '4px solid #C47A00' }}>
          <p className="mb-0 small">
            <strong>Datos históricos no disponibles.</strong>{' '}
            {hist.isConfigMissing
              ? 'Falta configurar VITE_API_BASE_URL en el frontend.'
              : 'La API requiere autenticación Bearer. Inicie sesión nuevamente si su sesión expiró.'}
          </p>
          <button
            onClick={hist.retry}
            className="border-0 bg-transparent fw-semibold"
            style={{ fontSize: 13, color: '#965D00', cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            Reintentar
          </button>
        </div>
      )}

      {/* Tendencias de temperatura y humedad (GET /history/readings/trends) */}
      <Row className="g-4 mb-4">
        <Col xs={12} lg={6}>
          <Card className="cc-card">
            <div className="cc-card-header">Temperatura promedio (°C) — {hist.rangeLabel.toLowerCase()}</div>
            <Card.Body>
              {hist.readingStatus === 'loading' ? (
                <div className="small text-muted">Cargando tendencias…</div>
              ) : hist.readingStatus === 'error' ? (
                <div className="small" style={{ color: '#B22F2F' }}>
                  No se pudieron cargar las tendencias. <button onClick={hist.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
                </div>
              ) : hist.readingTrends.length === 0 ? (
                <div className="small text-muted">Sin lecturas en el periodo.</div>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={hist.readingTrends.map(p => ({
                    t: bucketLabel(p.bucket, hist.range),
                    avg: p.avg_temp, min: p.min_temp, max: p.max_temp,
                  }))} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" />
                    <XAxis dataKey="t" tick={TICK_STYLE} interval="preserveStartEnd" minTickGap={48} />
                    <YAxis tick={TICK_STYLE} />
                    <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => v === null || v === undefined ? '—' : `${Number(v).toFixed(1)} °C`} />
                    <Legend {...LEGEND_STYLE} />
                    <Line type="monotone" dataKey="max" name="Máx" stroke="#C83B3B" strokeWidth={1} strokeDasharray="4 3" dot={false} connectNulls isAnimationActive={false} />
                    <Line type="monotone" dataKey="avg" name="Promedio" stroke="#123B5D" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
                    <Line type="monotone" dataKey="min" name="Mín" stroke="#1F6F8B" strokeWidth={1} strokeDasharray="4 3" dot={false} connectNulls isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card className="cc-card">
            <div className="cc-card-header">Humedad promedio (%) — {hist.rangeLabel.toLowerCase()}</div>
            <Card.Body>
              {hist.readingStatus === 'loading' ? (
                <div className="small text-muted">Cargando tendencias…</div>
              ) : hist.readingStatus === 'error' ? (
                <div className="small" style={{ color: '#B22F2F' }}>
                  No se pudieron cargar las tendencias. <button onClick={hist.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
                </div>
              ) : hist.readingTrends.length === 0 ? (
                <div className="small text-muted">Sin lecturas en el periodo.</div>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={hist.readingTrends.map(p => ({
                    t: bucketLabel(p.bucket, hist.range),
                    avg: p.avg_hum, min: p.min_hum, max: p.max_hum,
                  }))} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" />
                    <XAxis dataKey="t" tick={TICK_STYLE} interval="preserveStartEnd" minTickGap={48} />
                    <YAxis tick={TICK_STYLE} />
                    <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => v === null || v === undefined ? '—' : `${Number(v).toFixed(0)} %`} />
                    <Legend {...LEGEND_STYLE} />
                    <Line type="monotone" dataKey="max" name="Máx" stroke="#C47A00" strokeWidth={1} strokeDasharray="4 3" dot={false} connectNulls isAnimationActive={false} />
                    <Line type="monotone" dataKey="avg" name="Promedio" stroke="#1F6F8B" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
                    <Line type="monotone" dataKey="min" name="Mín" stroke="#27B3C2" strokeWidth={1} strokeDasharray="4 3" dot={false} connectNulls isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Evolución QoS (GET /history/qos/trends) */}
      <Card className="cc-card mb-4">
        <div className="cc-card-header">Evolución QoS — {hist.rangeLabel.toLowerCase()}</div>
        <Card.Body>
          <div className="d-flex flex-wrap gap-2 mb-3">
            {QOS_METRIC_OPTIONS.map(o => (
              <button key={o.key} type="button" onClick={() => setQosMetric(o.key)}
                className="rounded-2 border px-3 py-1"
                style={{ fontSize: 12, cursor: 'pointer', fontWeight: qosMetric === o.key ? 600 : 400,
                  background: qosMetric === o.key ? '#1F6F8B' : '#fff',
                  color: qosMetric === o.key ? '#fff' : '#52616B',
                  borderColor: qosMetric === o.key ? '#1F6F8B' : '#D9E2E8' }}>
                {o.label}
              </button>
            ))}
          </div>
          {hist.qosStatus === 'loading' ? (
            <div className="small text-muted">Cargando evolución QoS…</div>
          ) : hist.qosStatus === 'error' ? (
            <div className="small" style={{ color: '#B22F2F' }}>
              No se pudo cargar la evolución QoS. <button onClick={hist.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
            </div>
          ) : hist.qosTrends.length === 0 ? (
            <div className="small text-muted">Sin métricas QoS en el periodo.</div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={hist.qosTrends.map(p => ({
                t: bucketLabel(p.bucket, hist.range),
                v: qosValue(p, qosMetric),
              }))} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" />
                <XAxis dataKey="t" tick={TICK_STYLE} interval="preserveStartEnd" minTickGap={48} />
                <YAxis tick={TICK_STYLE} />
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => v === null || v === undefined ? '—' : qosFormat(qosMetric, Number(v))} />
                <Line type="monotone" dataKey="v" name={qosLabel(qosMetric)} stroke="#123B5D" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card.Body>
      </Card>

      {/* Distribuciones: criticidad (muestra), alertas/día (muestra), tipos y prioridades (summary) */}
      <Row className="g-4">
        <Col xs={12} lg={6}>
          <Card className="cc-card h-100">
            <div className="cc-card-header">Distribución de criticidad (muestra)</div>
            <Card.Body>
              {hist.classStatus === 'loading' ? (
                <div className="small text-muted">Cargando…</div>
              ) : hist.classStatus === 'error' ? (
                <div className="small" style={{ color: '#B22F2F' }}>
                  No se pudo cargar. <button onClick={hist.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
                </div>
              ) : (
                <>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={hist.criticalityBuckets} margin={CHART_MARGIN} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" horizontal={false} />
                      <XAxis type="number" tick={TICK_STYLE} allowDecimals={false} />
                      <YAxis type="category" dataKey="range" tick={TICK_STYLE} width={90} />
                      <Tooltip contentStyle={TOOLTIP_STYLE} />
                      <Bar dataKey="count" name="Clasificaciones" radius={[0, 3, 3, 0]} isAnimationActive={false}>
                        {hist.criticalityBuckets.map((e, i) => <Cell key={`cb-cell-${i}`} fill={e.color} />)}
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
        <Col xs={12} lg={6}>
          <Card className="cc-card h-100">
            <div className="cc-card-header">Alertas por día (muestra)</div>
            <Card.Body>
              {hist.alertsStatus === 'loading' ? (
                <div className="small text-muted">Cargando…</div>
              ) : hist.alertsStatus === 'error' ? (
                <div className="small" style={{ color: '#B22F2F' }}>
                  No se pudo cargar. <button onClick={hist.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
                </div>
              ) : hist.alertsPerDay.length === 0 ? (
                <div className="small text-muted">Sin alertas en el periodo.</div>
              ) : (
                <>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={hist.alertsPerDay} margin={CHART_MARGIN}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" />
                      <XAxis dataKey="day" tick={TICK_STYLE} interval="preserveStartEnd" minTickGap={24} />
                      <YAxis tick={TICK_STYLE} allowDecimals={false} />
                      <Tooltip contentStyle={TOOLTIP_STYLE} />
                      <Bar dataKey="count" name="Alertas" fill="#C83B3B" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                  <p className="text-muted mt-2 mb-0" style={{ fontSize: 11 }}>
                    Muestra de {hist.alertsSampleCount} alertas recientes, no el total global.
                  </p>
                </>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row className="g-4 mt-1">
        <Col xs={12} lg={4}>
          <Card className="cc-card h-100">
            <div className="cc-card-header">Alertas por tipo (acumulado backend)</div>
            <Card.Body>
              {hist.summaryStatus === 'loading' ? (
                <div className="small text-muted">Cargando…</div>
              ) : hist.summaryStatus === 'error' ? (
                <div className="small" style={{ color: '#B22F2F' }}>
                  No se pudo cargar. <button onClick={hist.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
                </div>
              ) : alertTypeEntries(hist.summary).length === 0 ? (
                <div className="small text-muted">Sin alertas registradas.</div>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={alertTypeEntries(hist.summary)} cx="50%" cy="50%" outerRadius={75} dataKey="value" isAnimationActive={false}>
                      {alertTypeEntries(hist.summary).map((e, i) => <Cell key={`at-cell-${i}`} fill={e.color} />)}
                    </Pie>
                    <Tooltip contentStyle={TOOLTIP_STYLE} />
                    <Legend {...LEGEND_STYLE} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </Card.Body>
          </Card>
        </Col>

        <Col xs={12} lg={4}>
          <Card className="cc-card h-100">
            <div className="cc-card-header">Distribución por prioridad (acumulado backend)</div>
            <Card.Body>
              {hist.summaryStatus === 'loading' ? (
                <div className="small text-muted">Cargando…</div>
              ) : hist.summaryStatus === 'error' ? (
                <div className="small" style={{ color: '#B22F2F' }}>No se pudo cargar.</div>
              ) : (
                <>
                  <div className="d-flex flex-column gap-3 pt-2">
                    {priorityEntries(hist.summary).map(p => (
                      <div key={p.name}>
                        <div className="d-flex justify-content-between mb-1">
                          <span className="fw-semibold" style={{ fontSize: 13 }}>{p.name}</span>
                          <span className="text-muted small">{p.value} ({p.pct}%)</span>
                        </div>
                        <div style={{ height: 10, background: '#EFF4F7', borderRadius: 5 }}>
                          <div style={{ height: '100%', width: `${p.pct}%`, background: p.color, borderRadius: 5 }} />
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="text-muted mt-4 mb-0" style={{ fontSize: 11 }}>
                    Total: {priorityEntries(hist.summary).reduce((s, p) => s + p.value, 0)} lecturas clasificadas
                  </p>
                </>
              )}
            </Card.Body>
          </Card>
        </Col>

        <Col xs={12} lg={4}>
          <Card className="cc-card h-100">
            <div className="cc-card-header">Distribución por cola (acumulado backend)</div>
            <Card.Body>
              {hist.summaryStatus === 'loading' ? (
                <div className="small text-muted">Cargando…</div>
              ) : hist.summaryStatus === 'error' ? (
                <div className="small" style={{ color: '#B22F2F' }}>No se pudo cargar.</div>
              ) : queueEntries(hist.summary).length === 0 ? (
                <div className="small text-muted">Sin datos de colas.</div>
              ) : (
                <>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={queueEntries(hist.summary)} margin={CHART_MARGIN} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" horizontal={false} />
                      <XAxis type="number" tick={TICK_STYLE} />
                      <YAxis type="category" dataKey="name" tick={TICK_STYLE} width={90} />
                      <Tooltip contentStyle={TOOLTIP_STYLE} />
                      <Bar dataKey="value" name="Lecturas" radius={[0, 3, 3, 0]} isAnimationActive={false}>
                        {queueEntries(hist.summary).map((e, i) => <Cell key={`qd-cell-${i}`} fill={e.color} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                  <p className="text-muted mt-2 mb-0" style={{ fontSize: 11 }}>
                    Total: {queueEntries(hist.summary).reduce((s, p) => s + p.value, 0)} lecturas clasificadas
                  </p>
                </>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {/* Indicadores derivados de /history/summary */}
      {hist.summary && (
        <Row className="g-3 mt-1">
          {summaryIndicators(hist.summary).map(m => (
            <Col key={m.label} xs={12} sm={6} xl={3}>
              <div className="cc-card p-3">
                <div className="small text-muted">{m.label}</div>
                <div style={{ fontSize: 22, fontWeight: 700, margin: '6px 0 4px' }}>{m.value}</div>
                <div className="small text-muted">{m.sub}</div>
              </div>
            </Col>
          ))}
        </Row>
      )}
    </div>
  );
}
