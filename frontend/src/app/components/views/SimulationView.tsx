import React, { useState } from 'react';
import { useNavigate } from 'react-router';
import { Play, Square, RotateCcw, ExternalLink, AlertTriangle, Cpu, Thermometer, Activity, Clock, Filter, Layers, Zap, Send, BarChart3, ArrowRight } from 'lucide-react';
import { Button, Card, Row, Col } from '../../lib/bootstrap';
import { useDevices, Device, DeviceType, DeviceStatus, DEVICE_TYPE_LABEL } from '../../contexts/DeviceContext';
import { useExperiments } from '../../contexts/ExperimentContext';

interface KpiCardProps { label: string; value: string | number; unit?: string; accent?: string; sub?: string; Icon?: any; }
function KpiCard({ label, value, unit, accent = '#123B5D', sub, Icon }: KpiCardProps) {
  return (
    <div className="cc-card p-3" style={{ borderTop: `3px solid ${accent}`, minWidth: 140 }}>
      <div className="d-flex justify-content-between align-items-start mb-1">
        <div className="small text-muted">{label}</div>
        {Icon && <Icon size={16} color={accent} />}
      </div>
      <div style={{ fontSize: 26, fontWeight: 700, margin: '6px 0 4px', color: '#17232D' }}>{value}{unit && <span style={{ fontSize: 14, fontWeight: 600, color: '#52616B' }}> {unit}</span>}</div>
      {sub && <div className="small text-muted">{sub}</div>}
    </div>
  );
}

interface DeviceCardProps { device: Device; isCritical: boolean; }
function DeviceCard({ device, isCritical }: DeviceCardProps) {
  const dotColor = isCritical ? '#C83B3B' : '#16835B';
  const typeLabel = DEVICE_TYPE_LABEL[device.device_type];
  return (
    <div className="rounded-3 p-3" style={{ border: '1px solid #D9E2E8', background: '#fff' }}>
      <div className="d-flex justify-content-between align-items-center mb-1">
        <span className="fw-semibold small">{device.name}</span>
        <span className="small d-flex align-items-center gap-1" style={{ color: dotColor, fontWeight: 600 }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: dotColor, display: 'inline-block' }} />
          {isCritical ? 'Crítico' : 'Normal'}
        </span>
      </div>
      <div className="small text-muted mb-1">{device.id} · {typeLabel} · {device.location}</div>
      <div className="small text-muted">Estado: {device.status}</div>
    </div>
  );
}

function FlowDiagram({ conPriorizacion }: { conPriorizacion: boolean }) {
  const allSteps = [
    { label: 'Dispositivos',  sub: 'cavas y vitrinas',     always: true,  Icon: Cpu },
    { label: 'Lecturas',      sub: 'temperatura/humedad',  always: true,  Icon: Thermometer },
    { label: 'Clasificación', sub: 'por criticidad',       always: false, Icon: Filter },
    { label: 'Priorización',  sub: 'gestión de colas',     always: false, Icon: Layers },
    { label: 'Procesamiento', sub: 'transformación',       always: true,  Icon: Zap },
    { label: 'Transmisión',   sub: 'hacia analytics',      always: true,  Icon: Send },
    { label: 'Resultados',    sub: 'métricas QoS',         always: true,  Icon: BarChart3 },
  ];
  const steps = conPriorizacion ? allSteps : allSteps.filter(s => s.always);
  return (
    <div className="d-flex align-items-center flex-wrap gap-2 justify-content-center">
      {steps.map((step, i) => (
        <div key={step.label} className="d-flex align-items-center gap-2">
          <div className="text-center p-2 rounded-3"
            style={{ border: '1px solid #D9E2E8', background: '#F5F8FA', minWidth: 96 }}>
            <step.Icon size={16} color="#123B5D" style={{ marginBottom: 4 }} />
            <div className="small fw-semibold" style={{ color: '#123B5D', fontSize: 12 }}>{step.label}</div>
            <div style={{ fontSize: 11, color: '#52616B' }}>{step.sub}</div>
          </div>
          {i < steps.length - 1 && <ArrowRight size={12} color="#D9E2E8" />}
        </div>
      ))}
    </div>
  );
}

export function SimulationView() {
  const navigate = useNavigate();
  const { devices } = useDevices();
  const { startRun, finishRun, metrics, activeRun, status: expStatus, retry: expRetry } = useExperiments();
  const [runId, setRunId] = useState<string | null>(null);

  const totalCavas    = devices.filter(d => d.device_type === 'cold_room').length;
  const totalVitrinas = devices.filter(d => d.device_type === 'refrigerated_showcase').length;

  const [procesamiento, setProcesamiento] = useState<'sin' | 'con'>('con');
  const [condicion,     setCondicion]     = useState<'normal' | 'critica'>('normal');
  const [running,       setRunning]       = useState(false);
  const [hasRun,        setHasRun]        = useState(false);
  const [runError,      setRunError]      = useState<string | null>(null);
  const [finishing,     setFinishing]     = useState(false);
  const [starting,      setStarting]      = useState(false);

  // Métricas reales de la ejecución finalizada (sin sondeo en vivo: el pipeline
  // del backend las registra mientras el run está activo y se leen al cerrar).
  const runMetrics = runId ? metrics.filter(m => m.run_id === runId) : [];
  const latestOf = (type: string): number | null => {
    const rows = runMetrics.filter(m => m.metric_type === type);
    if (rows.length === 0) return null;
    return [...rows].sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1))[0].value;
  };
  const avgOf = (type: string): number | null => {
    const rows = runMetrics.filter(m => m.metric_type === type);
    if (rows.length === 0) return null;
    return rows.reduce((s, m) => s + m.value, 0) / rows.length;
  };
  const fmt = (v: number | null, digits = 0): string =>
    v === null ? '—' : v.toLocaleString('es-CO', { maximumFractionDigits: digits, minimumFractionDigits: digits });

  const criticalDevices = devices.map(d => ({
    ...d,
    isCritical: condicion === 'critica' && (d.status === 'error'),
  }));
  const criticalCount = criticalDevices.filter(d => d.isCritical).length;

  async function handleEjecutar() {
    setRunError(null);
    setStarting(true);
    const { run, error } = await startRun({
      scenario: procesamiento === 'con' ? 'WITH_QOS' : 'WITHOUT_QOS',
      sensorCondition: condicion === 'critica' ? 'altered' : 'normal',
    });
    setStarting(false);
    if (!run) {
      setRunError(error ?? 'No se pudo iniciar la ejecución.');
      return;
    }
    setRunId(run.id);
    setHasRun(true);
    setRunning(true);
  }
  async function handleDetener() {
    if (!runId) return;
    setFinishing(true);
    const result = await finishRun(runId);
    setFinishing(false);
    if (!result.ok) {
      setRunError(result.error ?? 'No se pudo finalizar la ejecución.');
      return;
    }
    setRunning(false);
  }
  async function handleReiniciar() {
    if (runId && running) {
      await finishRun(runId);
    }
    setRunning(false);
    setRunId(null);
    setHasRun(false);
    setRunError(null);
    setProcesamiento('con'); setCondicion('normal');
  }

  return (
    <div>
      <div className="d-flex justify-content-between align-items-start flex-wrap gap-3 mb-3">
        <div>
          <h1 className="mb-1" style={{ fontSize: 20, fontWeight: 600 }}>Simulación — Ejecuciones experimentales</h1>
          <p className="text-muted small mb-0">
            Inicie ejecuciones reales contra el backend (POST /experiment-runs) y consulte sus métricas al finalizar.
          </p>
        </div>
        <Button variant="outline-primary" size="sm" className="d-flex align-items-center gap-2"
          onClick={() => navigate('/app/sensors')}>
          <ExternalLink size={14} />Ver dispositivos
        </Button>
      </div>

      {/* Environment summary */}
      <p className="text-muted small mb-4">
        {devices.length} dispositivos configurados · {totalCavas} Cavas · {totalVitrinas} Vitrinas
      </p>

      {activeRun && !runId && (
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-3 rounded-3 px-4 py-3 mb-4"
          style={{ background: '#EAF1F5', border: '1px solid #c5d9e6', borderLeft: '4px solid #1F6F8B' }}>
          <p className="mb-0 small">
            <strong>Hay una ejecución activa en el backend</strong> ({activeRun.scenario === 'WITH_QOS' ? 'con priorización' : 'sin priorización'}, iniciada {new Date(activeRun.started_at).toLocaleString('es-CO')}). Finalícela antes de iniciar otra.
          </p>
          <button
            onClick={() => { setRunId(activeRun.id); setHasRun(true); setRunning(true); }}
            className="border-0 bg-transparent fw-semibold"
            style={{ fontSize: 13, color: '#1F6F8B', cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            Retomar
          </button>
        </div>
      )}

      {expStatus === 'error' && !running && !hasRun && (
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-3 rounded-3 px-4 py-3 mb-4"
          style={{ background: '#FFF5E3', border: '1px solid #ffda6a', borderLeft: '4px solid #C47A00' }}>
          <p className="mb-0 small">
            <strong>No se pudieron cargar las ejecuciones.</strong> La API requiere autenticación Bearer. Inicie sesión nuevamente si su sesión expiró.
          </p>
          <button
            onClick={expRetry}
            className="border-0 bg-transparent fw-semibold"
            style={{ fontSize: 13, color: '#965D00', cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            Reintentar
          </button>
        </div>
      )}

      {/* Config panel */}
      {!running && !hasRun && (
        <Card className="cc-card mb-4">
          <div className="cc-card-header">Configuración del escenario</div>
          <Card.Body>
            <Row className="g-4 mb-4">
              <Col xs={12} lg={6}>
                <div className="small fw-semibold text-muted mb-3">Procesamiento</div>
                {(['con', 'sin'] as const).map(v => (
                  <label key={v} className="d-flex align-items-center gap-3 p-3 rounded-3 mb-2"
                    style={{
                      cursor: 'pointer',
                      border: `1px solid ${procesamiento === v ? '#123B5D' : '#D9E2E8'}`,
                      background: procesamiento === v ? '#F5F8FA' : '#fff',
                      transition: 'all 0.15s',
                    }}>
                    <input type="radio" name="proc" value={v} checked={procesamiento === v}
                      onChange={() => setProcesamiento(v)} style={{ accentColor: '#123B5D' }} />
                    <div>
                      <div className="fw-semibold small">
                        {v === 'con' ? 'Con priorización' : 'Sin priorización'}
                      </div>
                      <div style={{ fontSize: 12 }} className="text-muted">
                        {v === 'con'
                          ? 'Lecturas clasificadas por criticidad y encoladas (HIGH→WFQ, MEDIUM→Round Robin, LOW→FIFO).'
                          : 'Lecturas procesadas directamente sin clasificación ni priorización.'}
                      </div>
                    </div>
                  </label>
                ))}
              </Col>
              <Col xs={12} lg={6}>
                <div className="small fw-semibold text-muted mb-3">Condición del entorno</div>
                {(['normal', 'critica'] as const).map(v => (
                  <label key={v} className="d-flex align-items-center gap-3 p-3 rounded-3 mb-2"
                    style={{
                      cursor: 'pointer',
                      border: `1px solid ${condicion === v ? '#123B5D' : '#D9E2E8'}`,
                      background: condicion === v ? '#F5F8FA' : '#fff',
                      transition: 'all 0.15s',
                    }}>
                    <input type="radio" name="cond" value={v} checked={condicion === v}
                      onChange={() => setCondicion(v)}
                      style={{ accentColor: '#123B5D' }} />
                    <div>
                      <div className="fw-semibold small d-flex align-items-center gap-1">
                        {v === 'normal' ? 'Operación normal' : (
                          <><span style={{ width: 6, height: 6, borderRadius: '50%', background: '#C83B3B', display: 'inline-block' }} /><span>Condición crítica</span></>
                        )}
                      </div>
                      <div style={{ fontSize: 12 }} className="text-muted">
                        {v === 'normal'
                          ? 'Dispositivos con lecturas dentro de los rangos definidos por los umbrales.'
                          : 'Dispositivos en estado de error con lecturas fuera de rango — genera alertas TEMPERATURE_EXCEEDED y similares.'}
                      </div>
                    </div>
                  </label>
                ))}
              </Col>
            </Row>
            <Button variant="primary" className="d-flex align-items-center gap-2" onClick={handleEjecutar} disabled={starting}>
              <Play size={16} />{starting ? 'Iniciando…' : 'Iniciar simulación'}
            </Button>
            {runError && (
              <div className="rounded-3 px-3 py-2 mt-3 small" style={{ background: '#FCEEEE', border: '1px solid #f1aeb5', color: '#B22F2F' }}>
                {runError}
              </div>
            )}
            <p className="text-muted mt-3 mb-0" style={{ fontSize: 11 }}>
              Iniciar y finalizar requieren rol administrador en el backend. La condición del entorno es una etiqueta local de la ejecución.
            </p>
          </Card.Body>
        </Card>
      )}

      {/* Running state */}
      {(running || hasRun) && (
        <>
          <Row className="g-4 mb-4 align-items-center">
            <Col xs={12} lg={8}>
              <span className="small text-muted">
                {running ? 'Simulación en curso...' : 'Simulación finalizada'} ·{' '}
                {procesamiento === 'con' ? 'Con priorización' : 'Sin priorización'} ·{' '}
                {condicion === 'critica' ? 'Condición crítica' : 'Operación normal'}
              </span>
            </Col>
            <Col xs={12} lg={4} className="d-flex justify-content-lg-end">
              {running ? (
                <Button variant="danger" size="sm" className="d-flex align-items-center gap-2" onClick={handleDetener} disabled={finishing}>
                  <Square size={14} />{finishing ? 'Finalizando…' : 'Finalizar simulación'}
                </Button>
              ) : (
                <Button variant="secondary" size="sm" className="d-flex align-items-center gap-2" onClick={handleReiniciar}>
                  <RotateCcw size={14} />Nueva simulación
                </Button>
              )}
            </Col>
          </Row>

          {/* KPIs: métricas reales de la ejecución (último valor por tipo) */}
          <Row className="g-3 mb-4">
            <Col xs={12} sm={6} xl={4}><KpiCard label="Dispositivos" value={devices.length} Icon={Cpu} accent="#123B5D" sub={`${totalCavas} cavas · ${totalVitrinas} vitrinas`} /></Col>
            <Col xs={12} sm={6} xl={4}><KpiCard label="Mensajes recibidos" value={fmt(latestOf('messages_received'))} Icon={Thermometer} accent="#1F6F8B" sub={runMetrics.length > 0 ? `${runMetrics.length} muestras` : 'sin muestras aún'} /></Col>
            <Col xs={12} sm={6} xl={4}><KpiCard label="Lecturas persistidas" value={fmt(latestOf('readings_persisted'))} Icon={Activity} accent="#123B5D" sub="último valor" /></Col>
            <Col xs={12} sm={6} xl={4}><KpiCard label="Alertas generadas" value={fmt(latestOf('alerts_generated'))} Icon={AlertTriangle} accent={(latestOf('alerts_generated') ?? 0) > 0 ? '#C83B3B' : '#52616B'} sub="durante la ejecución" /></Col>
            <Col xs={12} sm={6} xl={4}><KpiCard label="Latencia ingesta→persistencia" value={fmt(avgOf('ingest_to_persist_ms'), 1)} unit="ms" Icon={Clock} accent="#123B5D" sub="promedio de muestras" /></Col>
            <Col xs={12} sm={6} xl={4}><KpiCard label="Backlog" value={fmt(latestOf('backlog'))} Icon={BarChart3} accent="#123B5D" sub="profundidad de cola" /></Col>
          </Row>
          {running && (
            <p className="text-muted small mb-4">
              Ejecución en curso en el backend. Las métricas las registra el pipeline; se leen al finalizar (sin sondeo en vivo).
            </p>
          )}
          {!running && hasRun && runMetrics.length === 0 && (
            <p className="text-muted small mb-4">
              La ejecución finalizó sin métricas registradas (el pipeline no reportó muestras para este run).
            </p>
          )}

          {/* Device status */}
          <Card className="cc-card mb-4">
            <div className="cc-card-header">
              Dispositivos del entorno
              {condicion === 'critica' && criticalCount > 0 && (
                <span className="small fw-semibold" style={{ color: '#C83B3B' }}>
                  · {criticalCount} en estado crítico
                </span>
              )}
            </div>
            <Card.Body>
              <Row className="g-2">
                {criticalDevices.map(d => (
                  <Col key={d.id} xs={12} sm={6} xl={4}>
                    <DeviceCard device={d} isCritical={d.isCritical} />
                  </Col>
                ))}
              </Row>
            </Card.Body>
          </Card>

          {/* Flow diagram */}
          <Card className="cc-card">
            <div className="cc-card-header">Flujo de procesamiento</div>
            <Card.Body>
              <FlowDiagram conPriorizacion={procesamiento === 'con'} />
              {procesamiento === 'sin' && (
                <p className="text-center small text-muted mt-3">
                  Los pasos de clasificación y priorización están omitidos. Las lecturas pasan directamente al procesamiento.
                </p>
              )}
            </Card.Body>
          </Card>
        </>
      )}
    </div>
  );
}
