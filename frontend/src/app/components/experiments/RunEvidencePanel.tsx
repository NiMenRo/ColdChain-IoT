import type { ExperimentEvidence, ExperimentRun, EvidenceLatency } from '../../types/experiments';
import { useRunEvidence } from '../../hooks/useRunEvidence';
import { InfoHelp } from './InfoHelp';

const P95_HELP = 'El promedio es el tiempo medio. El percentil 95 es un límite: aproximadamente el 95 % de las mediciones tardó ese tiempo o menos; el resto pudo tardar más. No es un porcentaje de éxito ni una garantía para pruebas futuras.';

const STATUS = {
  in_progress: 'Medición en curso',
  provisional: 'Resultados provisionales',
  final: 'Resultados finales',
  incomplete: 'Captura incompleta',
  unavailable: 'No disponible',
};

function value(number: number | null | undefined, unit = '') {
  return number === null || number === undefined || !Number.isFinite(number)
    ? 'No disponible'
    : `${number.toLocaleString('es-CO', { maximumFractionDigits: 2 })}${unit}`;
}

function latency(sample?: EvidenceLatency) {
  return sample?.count
    ? `Promedio: ${value(sample.mean, ' ms')} · El 95 % tardó como máximo ${value(sample.p95, ' ms')}`
    : 'No disponible';
}

export function EvidenceContent({ data, compact = false }: {
  data: ExperimentEvidence; compact?: boolean;
}) {
  const final = data.status === 'final';
  const metrics = [
    ['Mensajes enviados', value(data.counts.sent_unique)],
    ['Mensajes recibidos', value(data.counts.received_unique)],
    ['Duplicados recibidos', value(data.counts.duplicate_receptions)],
    [final ? 'No recibidos en la ventana' : 'No recibidos todavía (provisional)', value(data.pending_messages)],
    ['Lecturas guardadas', value(data.counts.database_readings_persisted)],
    ['Mensajes recibidos (%)', value(final ? data.pdr_percent : null, ' %')],
    ['No recibidos (%)', value(final ? data.loss_percent : null, ' %')],
    ['Volumen recibido', value(data.received_payload_bytes, ' B')],
    ['Velocidad de recepción', value(final ? data.payload_goodput_bytes_per_second : null, ' B/s')],
  ];
  return <>
    <p className="small fw-semibold mb-2" role="status">{STATUS[data.status]}</p>
    {data.reasons.map(reason => <p className="small text-muted mb-1" key={reason}>{reason}</p>)}
    <div className="row g-2 my-2">
      {(compact ? [metrics[0], metrics[1], metrics[4]] : metrics).map(([label, number]) => <div className="col-12 col-sm-6 col-xl-4" key={label}>
        <div className="border rounded-3 p-2 h-100">
          <div className="small text-muted">{label}</div>
          <div className="fw-semibold">{number}</div>
        </div>
      </div>)}
    </div>
    <div className="small mb-2">
      <div><strong>Desde el envío hasta guardar la lectura</strong>
        <InfoHelp label="tiempo desde el envío hasta guardar la lectura">{`Desde la emisión en el dispositivo hasta confirmar que la lectura quedó guardada. Incluye transporte, espera y procesamiento. ${P95_HELP}`}</InfoHelp>
        : {latency(data.device_to_persist_ms)}</div>
      <div><strong>Desde el envío hasta guardar la alerta</strong>
        <InfoHelp label="tiempo desde el envío hasta guardar la alerta">{`Desde la emisión hasta confirmar que la alerta quedó guardada. Solo incluye las muestras que generaron alerta; no mide la entrega de correo. ${P95_HELP}`}</InfoHelp>
        : {latency(data.device_to_alert_persist_ms)}</div>
      <div className="text-muted">El tiempo de alerta no incluye la entrega de correo.</div>
    </div>
    {!!data.clock_unmeasurable && <p className="small text-warning">
      No se pudo medir el tiempo de {data.clock_unmeasurable} muestras por diferencias de reloj o fechas no válidas.
    </p>}
    {!compact && <>
      <div className="table-responsive">
        <table className="table table-bordered table-sm small align-middle" style={{ minWidth: 520, borderColor: '#B8C8D4' }}>
          <caption>Tiempos por criticidad de las lecturas, con o sin priorización.</caption>
          <thead className="table-light"><tr><th scope="col">Criticidad</th><th scope="col">Hasta guardar lectura
            <InfoHelp label="tiempos por criticidad">{P95_HELP}</InfoHelp>
          </th><th scope="col">Hasta guardar alerta</th></tr></thead>
          <tbody>{([['high', 'Alta'], ['medium', 'Media'], ['low', 'Baja']] as const).map(([key, label]) =>
            <tr key={key}><th scope="row">{label}</th><td>{latency(data.by_priority[key]?.persist)}</td><td>{latency(data.by_priority[key]?.alert)}</td></tr>,
          )}</tbody>
        </table>
      </div>
    </>}
    <p className="small text-muted mb-0">
      {!final && 'Los porcentajes y la velocidad estarán disponibles cuando termine la medición completa.'}
    </p>
  </>;
}

export function RunEvidencePanel({ run, compact = false, title = 'Medición real de la ejecución' }: {
  run: ExperimentRun | null; compact?: boolean; title?: string;
}) {
  const evidence = useRunEvidence(run);
  return <section className="cc-card p-3 mb-3" aria-label={title}>
    <h3 className="mb-3" style={{ fontSize: 15, fontWeight: 600 }}>{title}</h3>
    {!run ? <p className="small text-muted">Seleccione una ejecución para consultar su evidencia.</p>
      : evidence.loading && !evidence.data ? <p className="small text-muted">Cargando medición real…</p>
      : evidence.error ? <div className="small" role="alert">
        No se pudo cargar la evidencia. {evidence.error}{' '}
        <button type="button" className="btn btn-sm btn-outline-primary" onClick={evidence.retry}>Reintentar</button>
      </div>
      : evidence.data ? <EvidenceContent data={evidence.data} compact={compact} />
      : <p className="small text-muted">No disponible.</p>}
    {run && evidence.data?.status !== 'final' && !evidence.error &&
      <button type="button" className="btn btn-sm btn-outline-secondary mt-2"
        disabled={evidence.loading} onClick={evidence.retry}>Actualizar medición</button>}
  </section>;
}
