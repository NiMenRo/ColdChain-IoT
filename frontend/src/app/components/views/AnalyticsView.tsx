import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';
import { LineChart, Line, BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie } from 'recharts';
import { Card, Row, Col } from '../../lib/bootstrap';
import { useExperiments } from '../../contexts/ExperimentContext';
import {
  ExperimentRun,
  ExperimentRunMeta,
} from '../../types/experiments';
import { CONDITION_LABELS, runCondition, suggestedCondition, type RunCondition } from '../../lib/runSelection';
import type { HistorySummary, QosTrendPoint } from '../../../services/api/history';
import { RANGE_OPTIONS, useHistoricalAnalytics, type HistoryRange } from '../../hooks/useHistoricalAnalytics';
import { alertLabel } from '../../hooks/useAlertsData';
import { formatMsValue, formatThroughput, secondsToMs } from '../../lib/qosUnits';
import { ComparisonResults } from '../experiments/AnalysisComparison';
import { comparisonInterval } from '../../lib/analysisSeries';
import { RunEvidencePanel } from '../experiments/RunEvidencePanel';

const CHART_MARGIN = { top: 4, right: 8, left: 0, bottom: 4 };
const TICK_STYLE   = { fill: '#52616B', fontSize: 11 };
const TOOLTIP_STYLE = { border: '1px solid #D9E2E8', borderRadius: '4px', fontSize: '12px' };
const LEGEND_STYLE  = { wrapperStyle: { fontSize: '12px' } };

function runNumber(runs: ExperimentRun[], run: ExperimentRun): number {
  const sorted = [...runs].sort((a, b) => a.started_at.localeCompare(b.started_at));
  return sorted.findIndex(r => r.id === run.id) + 1;
}

function runLabel(runs: ExperimentRun[], run: ExperimentRun, meta: Record<string, ExperimentRunMeta>): string {
  // Prioridad: meta local de sesión; si no, condición persistida en el snapshot.
  const condLabel = CONDITION_LABELS[runCondition(run, meta)];
  // Hora local del navegador (el backend persiste UTC): nunca slice crudo del ISO.
  const d = new Date(run.started_at);
  const when = Number.isNaN(d.getTime())
    ? run.started_at
    : d.toLocaleString('es-CO', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
  return `${condLabel} — Prueba #${runNumber(runs, run)} (${when})`;
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

function qosValue(p: QosTrendPoint, key: QosMetricKey): number | null {
  // Latencia/jitter se grafican en ms (el backend los persiste en segundos).
  // Un agregado NULL significa «sin muestras medibles»: se conserva como null
  // para que la serie deje un hueco, en vez de convertir null*1000 en 0.
  if (key === 'latency') return p.avg_latency === null ? null : secondsToMs(p.avg_latency);
  if (key === 'jitter') return p.avg_jitter === null ? null : secondsToMs(p.avg_jitter);
  if (key === 'packet_loss') return p.avg_packet_loss;
  if (key === 'throughput') return p.avg_throughput;
  return p.avg_pdr;
}

function qosFormat(key: QosMetricKey, v: number): string {
  if (key === 'latency' || key === 'jitter') return formatMsValue(v);
  if (key === 'throughput') return formatThroughput(v);
  return `${v.toFixed(1)} %`;
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
    { label: 'Lecturas registradas', value: String(summary.total_readings), sub: 'Total registrado' },
    { label: 'Clasificaciones', value: String(summary.total_classifications), sub: 'Total registrado' },
    { label: 'Métricas QoS', value: String(summary.total_qos_metrics), sub: 'Total registrado' },
    {
      label: 'Tipo de alerta predominante',
      value: topType ? alertLabel(topType[0]) : '—',
      sub: topType ? `${topType[1]} alertas · ${highPct}% del tráfico es HIGH` : 'Sin alertas registradas',
    },
  ];
}

export function AnalyticsView() {
  const { runs, intervalAnalyses = {}, runMeta, fetchAnalysis, status: expStatus, retry: expRetry } = useExperiments();
  const [searchParams] = useSearchParams();
  const requestedId = searchParams.get('run_id');
  const requested = runs.find(run => run.id === requestedId);
  const requestedUnknown = !!requested && runCondition(requested, runMeta) === 'unregistered';
  const unknownRuns = runs.filter(run => runCondition(run, runMeta) === 'unregistered');
  const [appliedId, setAppliedId] = useState(requested?.id ?? null);
  const [conditionInitialized, setConditionInitialized] = useState(runs.length > 0);
  const [condition, setCondition] = useState<RunCondition>(
    () => requested && !requestedUnknown ? runCondition(requested, runMeta) : suggestedCondition(runs, runMeta),
  );
  const [withQosId, setWithQosId] = useState<string | null>(
    requested?.scenario === 'WITH_QOS' ? requested.id : null,
  );
  const [withoutQosId, setWithoutQosId] = useState<string | null>(
    requested?.scenario === 'WITHOUT_QOS' ? requested.id : null,
  );
  useEffect(() => {
    if (!requested || appliedId === requested.id) return;
    setCondition(requestedUnknown ? suggestedCondition(runs, runMeta) : runCondition(requested, runMeta));
    setConditionInitialized(true);
    if (requested.scenario === 'WITH_QOS') setWithQosId(requested.id);
    else setWithoutQosId(requested.id);
    setAppliedId(requested.id);
  }, [requested, appliedId, runMeta, requestedUnknown, runs]);
  useEffect(() => {
    if (!conditionInitialized && runs.length && !requested) {
      setCondition(suggestedCondition(runs, runMeta));
      setConditionInitialized(true);
    }
  }, [conditionInitialized, runs, runMeta, requested]);

  // Sin condición no participa en comparaciones normales ni alteradas.
  const runsInCondition = useMemo(
    () => runs.filter(r => runCondition(r, runMeta) === condition),
    [runs, runMeta, condition],
  );
  const withQosRuns = runsInCondition.filter(r => r.scenario === 'WITH_QOS');
  const withoutQosRuns = runsInCondition.filter(r => r.scenario === 'WITHOUT_QOS');

  const withQosRun = withQosRuns.find(r => r.id === withQosId)
    ?? [...withQosRuns].sort((a, b) => Number(!!b.finished_at) - Number(!!a.finished_at) || b.started_at.localeCompare(a.started_at))[0]
    ?? null;
  const withoutQosRun = withoutQosRuns.find(r => r.id === withoutQosId)
    ?? [...withoutQosRuns].sort((a, b) => Number(!!b.finished_at) - Number(!!a.finished_at) || b.started_at.localeCompare(a.started_at))[0]
    ?? null;

  const [analysisAttempt, setAnalysisAttempt] = useState(0);
  const bucketSeconds = useMemo(() => comparisonInterval([withQosRun, withoutQosRun]),
    [withQosRun?.id, withoutQosRun?.id, withQosRun?.finished_at, withoutQosRun?.finished_at, analysisAttempt]);
  // Never present a cached series on a different temporal grid as this comparison.
  const withAnalysis = withQosRun ? intervalAnalyses[withQosRun.id]?.[bucketSeconds] : undefined;
  const withoutAnalysis = withoutQosRun ? intervalAnalyses[withoutQosRun.id]?.[bucketSeconds] : undefined;
  const [metricsError, setMetricsError] = useState<string | null>(null);

  // Métricas reales por ejecución seleccionada (lectura bajo demanda, sin sondeo).
  useEffect(() => {
    const ids = [withQosRun?.id, withoutQosRun?.id].filter((id): id is string => !!id);
    setMetricsError(null);
    if (ids.length === 0) return;
    let cancelled = false;
    Promise.all(ids.map(id => fetchAnalysis(id, bucketSeconds))).catch(() => {
      if (!cancelled) setMetricsError('No se pudieron cargar las estadísticas de las pruebas seleccionadas.');
    });
    return () => {
      cancelled = true;
    };
  }, [withQosRun?.id, withoutQosRun?.id, withQosRun?.finished_at, withoutQosRun?.finished_at, fetchAnalysis, analysisAttempt, bucketSeconds]);
  // Ámbito por ejecución para las gráficas históricas (null = global).
  // La sección comparativa usa sus propios selectores (métricas por run).
  const [trafficRunId, setTrafficRunId] = useState<string | null>(null);
  const hist = useHistoricalAnalytics(trafficRunId);
  const [qosMetric, setQosMetric] = useState<QosMetricKey>('latency');


  return (
    <div>
      <h1 className="mb-1" style={{ fontSize: 20, fontWeight: 600 }}>QoS — Análisis de Rendimiento</h1>
      <p className="text-muted small mb-4">
        Análisis del rendimiento y del histórico de la red de sensores.
      </p>

      {/* ─── Comparación experimental (ejecuciones reales del backend) ─── */}
      <h2 className="small fw-semibold text-muted text-uppercase mb-3" style={{ letterSpacing: '0.06em' }}>
        Comparación experimental
      </h2>

      {expStatus === 'loading' && (
        <div className="p-4 rounded-3 mb-4 text-center text-muted small" style={{ background: '#F5F8FA', border: '1px dashed #D9E2E8' }}>
          Cargando ejecuciones…
        </div>
      )}
      {expStatus === 'error' && (
        <div className="p-4 rounded-3 mb-4 text-center small" style={{ background: '#FFF5E3', border: '1px solid #ffda6a', color: '#965D00' }}>
          No se pudieron cargar las ejecuciones. <button onClick={expRetry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#965D00', cursor: 'pointer' }}>Reintentar</button>
        </div>
      )}
      {(expStatus === 'success' || expStatus === 'empty') && <>
      {requestedId && !requested && <p className="alert alert-warning small">
        La ejecución solicitada no está en la lista cargada. Seleccione una ejecución; no se sustituye su evidencia.
      </p>}
      {unknownRuns.length > 0 && <p className="alert alert-info small">
        Hay {unknownRuns.length} {unknownRuns.length === 1 ? 'prueba sin condición registrada' : 'pruebas sin condición registrada'}.
        Se conservan en el histórico, pero no se mezclan con las comparaciones de sensores normales o alterados.
      </p>}
      {requestedUnknown && requested && <RunEvidencePanel run={requested}
        title="Medición de la prueba enlazada — sin condición registrada" />}
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
                  {CONDITION_LABELS[c]}
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
                  <option key={r.id} value={r.id}>{runLabel(runs, r, runMeta)}</option>
                ))}
              </select>
            </Col>
            <Col xs={12} md={6}>
              <label className="small fw-semibold text-muted d-block mb-1">Ejecución sin priorización</label>
              <select className="form-select form-select-sm" value={withoutQosRun?.id ?? ''}
                onChange={e => setWithoutQosId(e.target.value || null)}>
                {withoutQosRuns.length === 0 && <option value="">Sin ejecuciones</option>}
                {withoutQosRuns.map(r => (
                  <option key={r.id} value={r.id}>{runLabel(runs, r, runMeta)}</option>
                ))}
              </select>
            </Col>
          </Row>

          <p className="small text-muted mb-0">
            Condición: <strong>{CONDITION_LABELS[condition]}</strong> · comparación
            {' '}<strong>Con priorización</strong> vs <strong>Sin priorización</strong>.
          </p>
        </Card.Body>
      </Card>

      <Row className="g-3 mb-3">
        <Col xs={12} xl={6}><RunEvidencePanel run={withQosRun} title="Medición real — Con priorización" /></Col>
        <Col xs={12} xl={6}><RunEvidencePanel run={withoutQosRun} title="Medición real — Sin priorización" /></Col>
      </Row>

      <ComparisonResults hasWith={!!withQosRun} hasWithout={!!withoutQosRun}
        conditionLabel={CONDITION_LABELS[condition]} withQos={withAnalysis} withoutQos={withoutAnalysis}
        error={metricsError} retry={() => setAnalysisAttempt(n => n + 1)} />
      </>}

      {/* ─── Análisis histórico — datos reales (TSK-052) ─── */}
      <hr className="my-5" style={{ borderColor: '#D9E2E8' }} />
      <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-1">
        <h2 className="mb-0" style={{ fontSize: 16, fontWeight: 600 }}>
          Análisis histórico
        </h2>
        <div className="d-flex align-items-center gap-3 flex-wrap">
          <div className="d-flex align-items-center gap-2 flex-wrap">
            <span className="small fw-semibold text-muted">Ejecución:</span>
            <select
              className="form-select form-select-sm"
              style={{ width: 'auto', minWidth: 220 }}
              value={trafficRunId ?? ''}
              onChange={(e) => setTrafficRunId(e.target.value || null)}
            >
              <option value="">Todas las ejecuciones</option>
              {[...runs]
                .sort((a, b) => b.started_at.localeCompare(a.started_at))
                .map((r) => (
                  <option key={r.id} value={r.id}>
                    {runLabel(runs, r, runMeta)}
                  </option>
                ))}
            </select>
          </div>
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
      </div>
      <p className="text-muted small mb-4">
        Datos de {hist.rangeLabel.toLowerCase()}
        {trafficRunId ? ' de la ejecución seleccionada' : ' (todas las ejecuciones)'}. Las
        distribuciones por criticidad y por día usan una muestra reciente, no el total global.
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
        <div className="cc-card-header">Evolución QoS v2 — {hist.rangeLabel.toLowerCase()}</div>
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
                <Line type="monotone" dataKey="v" name={qosLabel(qosMetric)} stroke="#123B5D" strokeWidth={2} dot={{ r: 2 }} connectNulls={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card.Body>
      </Card>

      {/* Distribuciones: criticidad (muestra), alertas/día (muestra), tipos y prioridades (summary) */}
      <Row className="g-4">
        <Col xs={12} lg={6}>
          <Card className="cc-card h-100">
            <div className="cc-card-header">Distribución de criticidad</div>
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
            <div className="cc-card-header">Alertas por día</div>
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
            <div className="cc-card-header">Alertas por tipo</div>
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
            <div className="cc-card-header">Distribución por prioridad</div>
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
                    Total: {priorityEntries(hist.summary).reduce((s, p) => s + p.value, 0)} clasificaciones (incluye legado)
                  </p>
                </>
              )}
            </Card.Body>
          </Card>
        </Col>

        <Col xs={12} lg={4}>
          <Card className="cc-card h-100">
            <div className="cc-card-header">Distribución por cola</div>
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
                      <Bar dataKey="value" name="Mensajes" radius={[0, 3, 3, 0]} isAnimationActive={false}>
                        {queueEntries(hist.summary).map((e, i) => <Cell key={`qd-cell-${i}`} fill={e.color} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                  <p className="text-muted mt-2 mb-0" style={{ fontSize: 11 }}>
                    Total: {queueEntries(hist.summary).reduce((s, p) => s + p.value, 0)} clasificaciones (incluye legado)
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
