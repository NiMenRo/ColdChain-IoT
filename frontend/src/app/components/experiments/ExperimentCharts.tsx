import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell,
} from 'recharts';
import { Card } from '../../lib/bootstrap';
import {
  ExperimentMetric,
  ExperimentRun,
  ExperimentScenario,
  COUNTER_METRICS,
  METRIC_LABELS,
  SCENARIO_LABELS,
} from '../../types/experiments';
import {
  sumMetric,
  delta,
  deltaPercent,
  seriesByElapsed,
  mergeLineSeries,
} from '../../lib/experimentAggregations';

const CHART_MARGIN = { top: 8, right: 12, left: 8, bottom: 24 };
const TICK_STYLE = { fill: '#52616B', fontSize: 11 };
const TOOLTIP_STYLE = { border: '1px solid #D9E2E8', borderRadius: '4px', fontSize: '12px' };
const LEGEND_STYLE = { wrapperStyle: { fontSize: '12px' } };

export const SCENARIO_COLORS: Record<ExperimentScenario, string> = {
  WITH_QOS: '#16835B',
  WITHOUT_QOS: '#C83B3B',
};

export const SCENARIO_BG: Record<ExperimentScenario, string> = {
  WITH_QOS: '#EAF6EF',
  WITHOUT_QOS: '#FCEEEE',
};

export function formatNumber(value: number): string {
  return value.toLocaleString('es-CO', { maximumFractionDigits: 2 });
}

export function ScenarioBadge({ scenario }: { scenario: ExperimentScenario }) {
  return (
    <span className="fw-semibold rounded-pill px-2 py-1"
      style={{ fontSize: 11, background: SCENARIO_BG[scenario], color: SCENARIO_COLORS[scenario], border: `1px solid ${SCENARIO_COLORS[scenario]}40` }}>
      {SCENARIO_LABELS[scenario]}
    </span>
  );
}

export function MetricComparisonCard({
  label,
  unit,
  withQosValue,
  withoutQosValue,
  higherIsBetter = false,
}: {
  label: string;
  unit: string;
  withQosValue: number | null;
  withoutQosValue: number | null;
  higherIsBetter?: boolean;
}) {
  const d = delta(withQosValue, withoutQosValue);
  const dPct = deltaPercent(withQosValue, withoutQosValue);
  const hasData = withQosValue !== null && withoutQosValue !== null;

  let deltaColor = '#52616B';
  let deltaLabel = '—';
  if (hasData) {
    const better = higherIsBetter ? d! > 0 : d! < 0;
    deltaColor = better ? '#16835B' : '#C83B3B';
    const sign = d! >= 0 ? '+' : '';
    deltaLabel = `${sign}${formatNumber(d!)} ${unit} (${sign}${dPct!.toFixed(1)}%)`;
  }

  return (
    <div className="p-3 rounded-3 d-flex flex-column gap-2" style={{ background: '#fff', border: '1px solid #EFF4F7' }}>
      <div className="d-flex justify-content-between align-items-baseline">
        <div className="small fw-semibold text-muted">{label}</div>
        <span className="fw-semibold" style={{ fontSize: 12, color: deltaColor }}>{deltaLabel}</span>
      </div>
      <div className="d-flex justify-content-between align-items-center">
        <span className="small" style={{ color: '#16835B' }}>Con priorización</span>
        <span className="fw-bold" style={{ fontSize: 18, color: '#17232D' }}>
          {withQosValue !== null ? formatNumber(withQosValue) : '—'} <span className="text-muted small fw-normal">{unit}</span>
        </span>
      </div>
      <div className="d-flex justify-content-between align-items-center">
        <span className="small" style={{ color: '#C83B3B' }}>Sin priorización</span>
        <span className="fw-bold" style={{ fontSize: 18, color: '#17232D' }}>
          {withoutQosValue !== null ? formatNumber(withoutQosValue) : '—'} <span className="text-muted small fw-normal">{unit}</span>
        </span>
      </div>
    </div>
  );
}

export function LineComparisonChart({
  title,
  data,
}: {
  title: string;
  data: { elapsedMin: number; withQos: number | null; withoutQos: number | null }[];
}) {
  return (
    <Card className="cc-card">
      <div className="cc-card-header">{title}</div>
      <Card.Body>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={data} margin={CHART_MARGIN}>
            <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" />
            <XAxis dataKey="elapsedMin" tick={TICK_STYLE} label={{ value: 'Minutos transcurridos', position: 'insideBottom', offset: -18, fill: '#52616B', fontSize: 11 }} />
            <YAxis tick={TICK_STYLE} />
            <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={(v: number) => `${v} min`} />
            <Legend {...LEGEND_STYLE} />
            <Line type="monotone" dataKey="withQos" name="Con priorización" stroke={SCENARIO_COLORS.WITH_QOS} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls={true} />
            <Line type="monotone" dataKey="withoutQos" name="Sin priorización" stroke={SCENARIO_COLORS.WITHOUT_QOS} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls={true} />
          </LineChart>
        </ResponsiveContainer>
      </Card.Body>
    </Card>
  );
}

export function BacklogChart({ withQosRun, withoutQosRun, allMetrics }: { withQosRun: ExperimentRun | null; withoutQosRun: ExperimentRun | null; allMetrics: ExperimentMetric[] }) {
  const withQosSeries = withQosRun ? seriesByElapsed(allMetrics, 'backlog', withQosRun.started_at) : [];
  const withoutQosSeries = withoutQosRun ? seriesByElapsed(allMetrics, 'backlog', withoutQosRun.started_at) : [];
  const merged = mergeLineSeries(withQosSeries, withoutQosSeries);

  return (
    <Card className="cc-card">
      <div className="cc-card-header">Backlog — Evolución temporal (profundidad de cola)</div>
      <Card.Body>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={merged} margin={CHART_MARGIN}>
            <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" />
            <XAxis dataKey="elapsedMin" tick={TICK_STYLE} label={{ value: 'Minutos transcurridos', position: 'insideBottom', offset: -18, fill: '#52616B', fontSize: 11 }} />
            <YAxis tick={TICK_STYLE} />
            <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={(v: number) => `${v} min`} />
            <Legend {...LEGEND_STYLE} />
            <Line type="monotone" dataKey="withQos" name="Con priorización" stroke={SCENARIO_COLORS.WITH_QOS} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls={true} />
            <Line type="monotone" dataKey="withoutQos" name="Sin priorización" stroke={SCENARIO_COLORS.WITHOUT_QOS} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls={true} />
          </LineChart>
        </ResponsiveContainer>
      </Card.Body>
    </Card>
  );
}

export function CountMetricsBarChart({ withQosRun, withoutQosRun, allMetrics }: { withQosRun: ExperimentRun | null; withoutQosRun: ExperimentRun | null; allMetrics: ExperimentMetric[] }) {
  const chartData = COUNTER_METRICS.map(type => ({
    metric: METRIC_LABELS[type],
    withQos: withQosRun ? sumMetric(allMetrics.filter(m => m.run_id === withQosRun.id), type) : 0,
    withoutQos: withoutQosRun ? sumMetric(allMetrics.filter(m => m.run_id === withoutQosRun.id), type) : 0,
  }));

  return (
    <Card className="cc-card">
      <div className="cc-card-header">Métricas de conteo — Comparación total</div>
      <Card.Body>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData} margin={CHART_MARGIN} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" horizontal={false} />
            <XAxis type="number" tick={TICK_STYLE} />
            <YAxis type="category" dataKey="metric" tick={TICK_STYLE} width={180} />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Legend {...LEGEND_STYLE} />
            <Bar dataKey="withQos" name="Con priorización" radius={[0, 3, 3, 0]} isAnimationActive={false}>
              <Cell fill={SCENARIO_COLORS.WITH_QOS} />
            </Bar>
            <Bar dataKey="withoutQos" name="Sin priorización" radius={[0, 3, 3, 0]} isAnimationActive={false}>
              <Cell fill={SCENARIO_COLORS.WITHOUT_QOS} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Card.Body>
    </Card>
  );
}

export function ConfigSnapshot({ config }: { config: string | null }) {
  if (!config) return <span className="text-muted small">Sin configuración</span>;
  try {
    const parsed = JSON.parse(config);
    return (
      <pre className="small text-muted" style={{ fontSize: 11, maxHeight: 120, overflow: 'auto', background: '#F5F8FA', padding: 8, borderRadius: 4 }}>
        {JSON.stringify(parsed, null, 2)}
      </pre>
    );
  } catch {
    return <span className="text-muted small">Configuración inválida</span>;
  }
}
