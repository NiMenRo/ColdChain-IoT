// Selector de ámbito por ejecución para gráficas históricas.
//
// - '' (Todas las ejecuciones) = comportamiento global actual, incluye
//   filas legado sin run. El backend filtra vía SensorReading.run_id /
//   Alert.run_id; el frontend nunca simula filtrado.
// - Con ejecución elegida, SOLO se envía run_id a endpoints que lo soportan
//   (history/*); las secciones en vivo (colas QoS) quedan fuera del ámbito
//   y se etiquetan como globales en su propia tarjeta.

import type { ExperimentRun } from '../types/experiments';

export function formatRunOption(run: ExperimentRun): string {
  const d = new Date(run.started_at);
  const when = Number.isNaN(d.getTime())
    ? run.started_at
    : d.toLocaleString('es-CO', {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
      });
  const scenario = run.scenario === 'WITH_QOS' ? 'Con priorización' : 'Sin priorización';
  const state = run.finished_at ? 'finalizada' : 'activa';
  return `${scenario} — ${when} (${state})`;
}

export function RunScopeSelector({
  runs,
  value,
  onChange,
  id,
}: {
  runs: ExperimentRun[];
  value: string | null;
  onChange: (runId: string | null) => void;
  id: string;
}) {
  const sorted = [...runs].sort((a, b) => b.started_at.localeCompare(a.started_at));
  return (
    <div className="d-flex align-items-center gap-2 flex-wrap">
      <label htmlFor={id} className="small fw-semibold text-muted">
        Ejecución:
      </label>
      <select
        id={id}
        className="form-select form-select-sm"
        style={{ width: 'auto', minWidth: 220 }}
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value || null)}
      >
        <option value="">Todas las ejecuciones</option>
        {sorted.map((r) => (
          <option key={r.id} value={r.id}>
            {formatRunOption(r)}
          </option>
        ))}
      </select>
    </div>
  );
}
