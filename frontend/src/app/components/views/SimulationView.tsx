import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router';
import { Play, Square, RotateCcw, ExternalLink, AlertTriangle, Info, Cpu, Thermometer, Activity, Clock, Wifi, Filter, Layers, Zap, Send, BarChart3, ArrowRight } from 'lucide-react';
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
  const { startRun, finishRun } = useExperiments();
  const activeRunIdRef = useRef<string | null>(null);

  const totalCavas    = devices.filter(d => d.device_type === 'cold_room').length;
  const totalVitrinas = devices.filter(d => d.device_type === 'refrigerated_showcase').length;

  const [procesamiento, setProcesamiento] = useState<'sin' | 'con'>('con');
  const [condicion,     setCondicion]     = useState<'normal' | 'critica'>('normal');
  const [running,       setRunning]       = useState(false);
  const [hasRun,        setHasRun]        = useState(false);
  const [kpis, setKpis] = useState({ generados: 0, procesados: 0, criticos: 0, latencia: 0, perdida: 0 });
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const criticalDevices = devices.map(d => ({
    ...d,
    isCritical: condicion === 'critica' && (d.status === 'error'),
  }));
  const criticalCount = criticalDevices.filter(d => d.isCritical).length;

  useEffect(() => {
    if (!running) return;
    const baseLat = procesamiento === 'con' ? 45 : 210;
    const basePct = procesamiento === 'con' ? 1.2 : 12.5;
    intervalRef.current = setInterval(() => {
      setKpis(prev => {
        const nuevos     = devices.length / 2;
        const criticos_  = condicion === 'critica' ? nuevos * 0.25 : nuevos * 0.03;
        const perdidaV   = basePct + (Math.random() - 0.5) * 0.8;
        const procesados_ = nuevos * (1 - perdidaV / 100);
        return {
          generados:  Math.round(prev.generados  + nuevos),
          procesados: Math.round(prev.procesados + procesados_),
          criticos:   Math.round(prev.criticos   + criticos_),
          latencia:   Math.round(baseLat + (Math.random() - 0.5) * 12),
          perdida:    Math.round(perdidaV * 10) / 10,
        };
      });
    }, 500);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [running, procesamiento, condicion, devices]);

  function handleEjecutar() {
    setKpis({ generados: 0, procesados: 0, criticos: 0, latencia: 0, perdida: 0 });
    setHasRun(true);
    const run = startRun({
      scenario: procesamiento === 'con' ? 'WITH_QOS' : 'WITHOUT_QOS',
      sensorCondition: condicion === 'critica' ? 'altered' : 'normal',
    });
    activeRunIdRef.current = run ? run.id : null;
    setRunning(true);
  }
  function handleDetener() {
    setRunning(false);
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (activeRunIdRef.current) { finishRun(activeRunIdRef.current); activeRunIdRef.current = null; }
  }
  function handleReiniciar() {
    setRunning(false);
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (activeRunIdRef.current) { finishRun(activeRunIdRef.current); activeRunIdRef.current = null; }
    setKpis({ generados: 0, procesados: 0, criticos: 0, latencia: 0, perdida: 0 });
    setHasRun(false);
    setProcesamiento('con'); setCondicion('normal');
  }

  return (
    <div>
      <div className="d-flex justify-content-between align-items-start flex-wrap gap-3 mb-3">
        <div>
          <h1 className="mb-1" style={{ fontSize: 20, fontWeight: 600 }}>Simulación — Demostración del prototipo</h1>
          <p className="text-muted small mb-0">
            Experiencia conceptual para evaluar el flujo de datos bajo diferentes condiciones. Los datos son mock y no persisten en backend.
          </p>
        </div>
        <Button variant="outline-primary" size="sm" className="d-flex align-items-center gap-2"
          onClick={() => navigate('/app/sensors')}>
          <ExternalLink size={14} />Ver dispositivos
        </Button>
      </div>

      {/* Demo notice */}
      <div className="d-flex align-items-start gap-2 rounded-3 px-4 py-3 mb-4"
        style={{ background: '#F5F8FA', border: '1px solid #D9E2E8' }}>
        <Info size={15} style={{ color: '#52616B', flexShrink: 0, marginTop: 2 }} />
        <p className="mb-0 small" style={{ color: '#52616B' }}>
          Esta pantalla es una <strong style={{ color: '#17232D' }}>demostración conceptual</strong> del prototipo. Los controles de escenario generan datos mock deterministas para evaluar la experiencia visual. No existe una API REST de simulación en el backend actual.
        </p>
      </div>

      {/* Environment summary */}
      <p className="text-muted small mb-4">
        {devices.length} dispositivos configurados · {totalCavas} Cavas · {totalVitrinas} Vitrinas
      </p>

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
            <Button variant="primary" className="d-flex align-items-center gap-2" onClick={handleEjecutar}>
              <Play size={16} />Iniciar simulación
            </Button>
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
                <Button variant="danger" size="sm" className="d-flex align-items-center gap-2" onClick={handleDetener}>
                  <Square size={14} />Finalizar simulación
                </Button>
              ) : (
                <Button variant="secondary" size="sm" className="d-flex align-items-center gap-2" onClick={handleReiniciar}>
                  <RotateCcw size={14} />Nueva simulación
                </Button>
              )}
            </Col>
          </Row>

          {/* KPIs */}
          <Row className="g-3 mb-4">
            <Col xs={12} sm={6} xl={4}><KpiCard label="Dispositivos" value={devices.length} Icon={Cpu} accent="#123B5D" sub={`${totalCavas} cavas · ${totalVitrinas} vitrinas`} /></Col>
            <Col xs={12} sm={6} xl={4}><KpiCard label="Lecturas generadas" value={kpis.generados.toLocaleString()} Icon={Thermometer} accent="#1F6F8B" sub="acumuladas" /></Col>
            <Col xs={12} sm={6} xl={4}><KpiCard label="Lecturas procesadas" value={kpis.procesados.toLocaleString()} Icon={Activity} accent="#123B5D" sub="acumuladas" /></Col>
            <Col xs={12} sm={6} xl={4}><KpiCard label="Críticas detectadas" value={kpis.criticos.toLocaleString()} Icon={AlertTriangle} accent={kpis.criticos > 0 ? '#C83B3B' : '#52616B'} sub="durante la ejecución" /></Col>
            <Col xs={12} sm={6} xl={4}><KpiCard label="Latencia" value={kpis.latencia} unit="ms" Icon={Clock} accent="#123B5D" sub="últimos 500 ms" /></Col>
            <Col xs={12} sm={6} xl={4}><KpiCard label="Pérdida de paquetes" value={kpis.perdida} unit="%" Icon={Wifi} accent={kpis.perdida < 5 ? '#16835B' : '#C83B3B'} sub="último intervalo" /></Col>
          </Row>

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
