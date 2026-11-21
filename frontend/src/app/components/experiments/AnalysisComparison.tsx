import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import type { ExperimentAnalysis, ExperimentMetricType } from '../../types/experiments';
import { METRIC_LABELS } from '../../types/experiments';
import { MetricComparisonCard } from './ExperimentCharts';
import { AnalysisLineChart } from './AnalysisLineChart';
import { InfoHelp } from './InfoHelp';

const COUNTS: ExperimentMetricType[] = ['messages_received', 'readings_persisted', 'alerts_generated', 'readings_failed'];
const LATENCIES: ExperimentMetricType[] = ['ingest_to_persist_ms', 'ingest_to_alert_ms', 'queue_wait_ms', 'service_time_ms'];
const LABELS: Partial<Record<ExperimentMetricType, string>> = {
  ingest_to_persist_ms: 'Tiempo desde recepción hasta guardar',
  ingest_to_alert_ms: 'Tiempo desde recepción hasta crear alerta',
  queue_wait_ms: 'Espera antes de atender', service_time_ms: 'Tiempo de atención',
};
const HELP: Partial<Record<ExperimentMetricType, string>> = {
  ingest_to_persist_ms: 'Tiempo desde que el backend recibe el mensaje hasta confirmar que la lectura está guardada. Incluye espera y procesamiento, pero no el transporte desde el dispositivo. El promedio resume todas las muestras; el máximo es la mayor demora observada.',
  ingest_to_alert_ms: 'Tiempo desde que el backend recibe el mensaje hasta crear la alerta dentro del procesamiento. Solo hay muestras cuando se genera una alerta. No mide la entrega de correo ni es igual al tiempo desde el envío hasta guardar la alerta.',
  queue_wait_ms: 'Tiempo que una lectura admitida espera hasta que comienza su atención. No incluye el tiempo de transporte ni el trabajo posterior de procesamiento.',
  service_time_ms: 'Tiempo desde que empieza la atención de la lectura hasta que termina el procesamiento instrumentado. No incluye su espera anterior en la cola.',
  backlog: 'Cantidad de elementos pendientes observada en cada muestra. La línea muestra el promedio por intervalo; Ver máximos permite consultar los picos sin confundirlos con el promedio. No es un total acumulado.',
};
const ms = (value: number | undefined) => value === undefined ? 'No disponible'
  : `${value.toLocaleString('es-CO', { maximumFractionDigits: 2 })} ms`;

export function AnalysisComparison({ withQos, withoutQos }: {
  withQos: ExperimentAnalysis; withoutQos: ExperimentAnalysis;
}) {
  const counts = COUNTS.map(type => ({metric: METRIC_LABELS[type],
    withQos: withQos.metrics[type]?.sum ?? null, withoutQos: withoutQos.metrics[type]?.sum ?? null}));
  return <>
    {(withQos.provisional || withoutQos.provisional) && <p className="alert alert-info small">
      Hay una prueba en curso. Sus resultados todavía pueden cambiar.
    </p>}
    <h3 className="small fw-semibold">Resumen de procesamiento</h3>
    <div className="row g-3 mb-4">{COUNTS.map(type => <div className="col-sm-6 col-xl-3" key={type}>
      <MetricComparisonCard label={METRIC_LABELS[type]} unit={type === 'messages_received' ? 'mensajes' : type === 'alerts_generated' ? 'alertas' : 'lecturas'}
        higherIsBetter={type === 'messages_received' || type === 'readings_persisted'}
        withQosValue={withQos.metrics[type]?.sum ?? null} withoutQosValue={withoutQos.metrics[type]?.sum ?? null} />
    </div>)}</div>
    <h3 className="small fw-semibold">Tiempos de procesamiento</h3>
    <div className="row g-3 mb-4">{LATENCIES.map(type => <div className="col-md-6" key={type}>
      <div className="cc-card p-3">
        <h4 className="small fw-semibold">{LABELS[type]}
          <InfoHelp label={LABELS[type]!}>{HELP[type]!}</InfoHelp>
        </h4>
        <div className="table-responsive">
          <table className="table table-bordered table-sm small align-middle mb-0" style={{minWidth: 360, borderColor: '#B8C8D4'}}>
            <thead className="table-light"><tr><th scope="col">Prueba</th><th scope="col">Promedio</th><th scope="col">Máximo</th></tr></thead>
            <tbody>
              <tr><th scope="row">Con priorización</th><td className="text-end text-nowrap">{ms(withQos.metrics[type]?.mean)}</td><td className="text-end text-nowrap">{ms(withQos.metrics[type]?.max)}</td></tr>
              <tr><th scope="row">Sin priorización</th><td className="text-end text-nowrap">{ms(withoutQos.metrics[type]?.mean)}</td><td className="text-end text-nowrap">{ms(withoutQos.metrics[type]?.max)}</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>)}</div>
    <p className="small text-muted">
      Los totales y promedios incluyen todas las mediciones de cada prueba.
      Las gráficas agrupan las mediciones por intervalos para facilitar su lectura.
      Una diferencia por sí sola no demuestra una mejora por priorización.
    </p>
    <div className="row g-3 mb-4">
      {(['ingest_to_persist_ms', 'ingest_to_alert_ms', 'backlog'] as const).map(type => <div className="col-lg-6" key={type}>
        {(withQos.series[type]?.length || withoutQos.series[type]?.length)
          ? <AnalysisLineChart title={type === 'backlog' ? 'Mensajes en espera' : LABELS[type]!}
            help={`${HELP[type]} Cada punto agrupa las mediciones del mismo intervalo desde el inicio de cada prueba. Consulte el promedio, máximo y número de mediciones al señalar el punto; puede alternar a Ver máximos. Los intervalos sin datos no equivalen a cero.`}
            unit={type === 'backlog' ? '' : 'ms'} withQos={withQos.series[type] ?? []}
            withoutQos={withoutQos.series[type] ?? []} bucketSeconds={withQos.bucket_seconds} />
          : <div className="cc-card p-3 small">{LABELS[type] ?? 'Mensajes en espera'}: sin mediciones para graficar.</div>}
      </div>)}
      <div className="col-lg-6"><div className="cc-card p-3">
        <h4 className="small fw-semibold">Mensajes, lecturas y alertas procesadas
          <InfoHelp label="mensajes, lecturas y alertas procesadas">Totales completos de cada prueba, no de una página ni de una muestra. Un mensaje puede contener varias lecturas y no toda lectura genera una alerta. Si las pruebas duran tiempos distintos, sus totales no prueban por sí solos una mejora.</InfoHelp>
        </h4>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={counts} layout="vertical" margin={{left: 20, bottom: 12, right: 12}}>
            <XAxis type="number" /><YAxis type="category" dataKey="metric" width={145} tick={{fontSize: 11}} />
            <Tooltip /><Legend />
            <Bar dataKey="withQos" name="Con priorización" fill="#16835B" isAnimationActive={false} />
            <Bar dataKey="withoutQos" name="Sin priorización" fill="#C83B3B" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div></div>
    </div>
  </>;
}

export function ComparisonResults({ hasWith, hasWithout, conditionLabel, withQos, withoutQos, error, retry }: {
  hasWith: boolean; hasWithout: boolean; conditionLabel: string;
  withQos?: ExperimentAnalysis; withoutQos?: ExperimentAnalysis;
  error: string | null; retry: () => void;
}) {
  return <>
    {error && <div className="alert alert-warning">{error}{' '}
      <button className="btn btn-sm btn-outline-primary" onClick={retry}>Reintentar</button>
    </div>}
    {hasWith && hasWithout ? (
      !error && (!withQos || !withoutQos
        ? <p className="small text-muted">Cargando estadísticas…</p>
        : withQos.total_samples === 0 || withoutQos.total_samples === 0
          ? <p className="alert alert-info small">Una de las pruebas seleccionadas no tiene mediciones guardadas.</p>
          : <AnalysisComparison withQos={withQos} withoutQos={withoutQos} />)
    ) : (
      <div className="p-4 rounded-3 mb-4 text-center text-muted small" style={{background: '#F5F8FA', border: '1px dashed #D9E2E8'}}>
        Falta una prueba {hasWith ? 'sin' : 'con'} priorización bajo la condición <strong>{conditionLabel}</strong>.
        Selecciona otra condición o ejecuta la prueba que falta desde Simulación.
      </div>
    )}
  </>;
}
