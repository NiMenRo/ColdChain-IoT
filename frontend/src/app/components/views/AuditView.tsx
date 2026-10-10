import { useState, useMemo, useRef, useEffect } from 'react';
import { CheckCircle, XCircle, Calendar, ChevronLeft, ChevronRight, X, Eye } from 'lucide-react';
import { Card, Button, Form, Row, Col } from '../../lib/bootstrap';
import { AuditLog, AuditAction, AuditResult, AUDIT_ACTIONS } from '../../types/audit';
import { useAuditLogs } from '../../hooks/useAuditLogs';

function ResultBadge({ result }: { result: AuditResult }) {
  const ok = result === 'success';
  return (
    <span className="d-inline-flex align-items-center gap-1 rounded-pill px-2 fw-semibold"
      style={{ fontSize: 12, background: ok ? '#EAF6EF' : '#FCEEEE', color: ok ? '#16835B' : '#B22F2F' }}>
      {ok ? <CheckCircle size={11} /> : <XCircle size={11} />}
      {ok ? 'success' : 'failure'}
    </span>
  );
}

function formatTs(ts: string) {
  return new Date(ts).toLocaleString('es-CO', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function ActionBadge({ action }: { action: AuditAction }) {
  return (
    <code style={{ fontSize: 11, background: '#EAF1F5', padding: '2px 6px', borderRadius: 3, color: '#123B5D' }}>
      {action}
    </code>
  );
}

function JsonDisplay({ value }: { value: string | null }) {
  if (!value) return <span className="text-muted small fst-italic">(null)</span>;
  try {
    const parsed = JSON.parse(value);
    return (
      <pre className="small mb-0" style={{ fontSize: 11, maxHeight: 200, overflow: 'auto', background: '#F5F8FA', padding: 8, borderRadius: 4, fontFamily: 'monospace' }}>
        {JSON.stringify(parsed, null, 2)}
      </pre>
    );
  } catch {
    return <code className="small" style={{ color: '#52616B' }}>{value}</code>;
  }
}

function ResourceBadge({ resource }: { resource: string }) {
  return <code className="small" style={{ color: '#52616B' }}>{resource}</code>;
}

// ─── Calendar Picker ──────────────────────────────────────────────────────────
const MONTH_NAMES = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                     'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
const DAY_NAMES   = ['Lu','Ma','Mi','Ju','Vi','Sa','Do'];

function getDaysInMonth(year: number, month: number) { return new Date(year, month + 1, 0).getDate(); }
function getFirstDayOfWeek(year: number, month: number) {
  const d = new Date(year, month, 1).getDay();
  return d === 0 ? 6 : d - 1; // Monday = 0
}

interface CalendarPickerProps {
  value: string;       // 'YYYY-MM-DD' or ''
  onChange: (v: string) => void;
  placeholder?: string;
  align?: 'left' | 'right';
}
function CalendarPicker({ value, onChange, placeholder = 'Seleccionar fecha', align = 'left' }: CalendarPickerProps) {
  const [open, setOpen] = useState(false);
  const today = new Date();
  const [viewYear,  setViewYear]  = useState(value ? parseInt(value.slice(0,4)) : today.getFullYear());
  const [viewMonth, setViewMonth] = useState(value ? parseInt(value.slice(5,7)) - 1 : today.getMonth());
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  function prevMonth() {
    if (viewMonth === 0) { setViewMonth(11); setViewYear(y => y - 1); }
    else setViewMonth(m => m - 1);
  }
  function nextMonth() {
    if (viewMonth === 11) { setViewMonth(0); setViewYear(y => y + 1); }
    else setViewMonth(m => m + 1);
  }

  function selectDay(day: number) {
    const mm = String(viewMonth + 1).padStart(2, '0');
    const dd = String(day).padStart(2, '0');
    onChange(`${viewYear}-${mm}-${dd}`);
    setOpen(false);
  }

  function clear(e: React.MouseEvent) {
    e.stopPropagation();
    onChange('');
  }

  function goToday() {
    const t = today;
    setViewYear(t.getFullYear());
    setViewMonth(t.getMonth());
    const mm = String(t.getMonth() + 1).padStart(2, '0');
    const dd = String(t.getDate()).padStart(2, '0');
    onChange(`${t.getFullYear()}-${mm}-${dd}`);
    setOpen(false);
  }

  const daysInMonth  = getDaysInMonth(viewYear, viewMonth);
  const firstDaySlot = getFirstDayOfWeek(viewYear, viewMonth);
  const totalCells   = Math.ceil((firstDaySlot + daysInMonth) / 7) * 7;

  const selY = value ? parseInt(value.slice(0,4)) : null;
  const selM = value ? parseInt(value.slice(5,7)) - 1 : null;
  const selD = value ? parseInt(value.slice(8,10)) : null;

  const todayY = today.getFullYear();
  const todayM = today.getMonth();
  const todayD = today.getDate();

  const displayValue = value
    ? `${value.slice(8,10)}/${value.slice(5,7)}/${value.slice(0,4)}`
    : '';

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      {/* Trigger */}
      <button type="button" onClick={() => setOpen(o => !o)}
        className="form-control form-control-sm d-flex align-items-center gap-2 text-start"
        style={{ cursor: 'pointer', minWidth: 160 }}>
        <Calendar size={13} style={{ color: '#52616B', flexShrink: 0 }} />
        <span className="flex-grow-1" style={{ fontSize: 13, color: displayValue ? '#17232D' : '#6c757d' }}>
          {displayValue || placeholder}
        </span>
        {value && (
          <span onClick={clear} style={{ cursor: 'pointer', color: '#6c757d', lineHeight: 1 }}>
            <X size={12} />
          </span>
        )}
      </button>

      {/* Popover */}
      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 6px)',
          [align === 'right' ? 'right' : 'left']: 0,
          zIndex: 1040, background: '#fff',
          border: '1px solid #D9E2E8', borderRadius: 10,
          padding: '12px 12px 10px',
          boxShadow: '0 4px 24px rgba(0,0,0,0.13)',
          minWidth: 248,
        }}>
          {/* Month navigation */}
          <div className="d-flex align-items-center justify-content-between mb-2">
            <button type="button" onClick={prevMonth}
              className="border-0 bg-transparent rounded p-1 d-flex align-items-center"
              style={{ cursor: 'pointer', color: '#52616B' }}>
              <ChevronLeft size={16} />
            </button>
            <span className="fw-semibold" style={{ fontSize: 13, color: '#17232D' }}>
              {MONTH_NAMES[viewMonth]} {viewYear}
            </span>
            <button type="button" onClick={nextMonth}
              className="border-0 bg-transparent rounded p-1 d-flex align-items-center"
              style={{ cursor: 'pointer', color: '#52616B' }}>
              <ChevronRight size={16} />
            </button>
          </div>

          {/* Day headers */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '2px', marginBottom: 4 }}>
            {DAY_NAMES.map(d => (
              <div key={d} style={{ textAlign: 'center', fontSize: 11, fontWeight: 600, color: '#52616B', padding: '2px 0' }}>{d}</div>
            ))}
          </div>

          {/* Day cells */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '2px' }}>
            {Array.from({ length: totalCells }, (_, i) => {
              const dayNum = i - firstDaySlot + 1;
              const isValid = dayNum >= 1 && dayNum <= daysInMonth;
              const isSelected = isValid && selY === viewYear && selM === viewMonth && selD === dayNum;
              const isToday    = isValid && todayY === viewYear && todayM === viewMonth && todayD === dayNum;
              return (
                <button key={i} type="button"
                  disabled={!isValid}
                  onClick={() => isValid && selectDay(dayNum)}
                  style={{
                    border: isToday && !isSelected ? '1px solid #27B3C2' : 'none',
                    borderRadius: 6, padding: '5px 0', fontSize: 12, textAlign: 'center', cursor: isValid ? 'pointer' : 'default',
                    background:  isSelected ? '#123B5D' : 'transparent',
                    color:       isSelected ? '#fff' : isValid ? '#17232D' : 'transparent',
                    fontWeight:  isSelected ? 700 : isToday ? 600 : 400,
                    opacity:     isValid ? 1 : 0,
                  }}>
                  {isValid ? dayNum : ''}
                </button>
              );
            })}
          </div>

          {/* Footer */}
          <div className="d-flex justify-content-center mt-2 pt-2" style={{ borderTop: '1px solid #EFF4F7' }}>
            <button type="button" onClick={goToday}
              className="border-0 bg-transparent fw-semibold"
              style={{ fontSize: 11, color: '#1F6F8B', cursor: 'pointer' }}>
              Hoy
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Detail Modal ─────────────────────────────────────────────────────────────
function OverlayModal({ show, onHide, title, children }: {
  show: boolean; onHide: () => void; title: string; children: React.ReactNode;
}) {
  if (!show) return null;
  return (
    <div onClick={onHide}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1050,
               display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div onClick={e => e.stopPropagation()}
        style={{ background: '#fff', borderRadius: 12, width: '100%', maxWidth: 640,
                 maxHeight: '90vh', overflowY: 'auto',
                 boxShadow: '0 8px 40px rgba(0,0,0,0.18)' }}>
        <div className="d-flex justify-content-between align-items-center px-4 py-3"
          style={{ borderBottom: '1px solid #EFF4F7' }}>
          <h2 className="mb-0" style={{ fontSize: 16, fontWeight: 600 }}>{title}</h2>
          <button className="border-0 bg-transparent p-1 rounded" onClick={onHide}
            style={{ cursor: 'pointer', color: '#52616B' }}><X size={18} /></button>
        </div>
        <div className="px-4 py-3">{children}</div>
      </div>
    </div>
  );
}

interface DetailModalProps {
  log: AuditLog | null;
  onClose: () => void;
}
function DetailModal({ log, onClose }: DetailModalProps) {
  if (!log) return null;

  return (
    <OverlayModal show={true} onHide={onClose} title={`Detalle de auditoría — ${log.id}`}>
      <div className="row g-3 mb-4">
        <Col xs={12} sm={6}>
          <div className="small text-muted mb-1">ID</div>
          <code className="small font-monospace">{log.id}</code>
        </Col>
        <Col xs={12} sm={6}>
          <div className="small text-muted mb-1">Fecha</div>
          <div className="small font-monospace">{formatTs(log.timestamp)}</div>
        </Col>
        <Col xs={12} sm={6}>
          <div className="small text-muted mb-1">Actor</div>
          <div className="small">{log.actor}</div>
        </Col>
        <Col xs={12} sm={6}>
          <div className="small text-muted mb-1">Acción</div>
          <ActionBadge action={log.action} />
        </Col>
        <Col xs={12} sm={6}>
          <div className="small text-muted mb-1">Recurso</div>
          <ResourceBadge resource={log.resource} />
        </Col>
        <Col xs={12} sm={6}>
          <div className="small text-muted mb-1">Resultado</div>
          <ResultBadge result={log.result} />
        </Col>
      </div>

      <div className="row g-3">
        <Col xs={12} lg={6}>
          <div className="small text-muted mb-1">Valor anterior (old_value)</div>
          <JsonDisplay value={log.old_value} />
        </Col>
        <Col xs={12} lg={6}>
          <div className="small text-muted mb-1">Valor nuevo (new_value)</div>
          <JsonDisplay value={log.new_value} />
        </Col>
      </div>
    </OverlayModal>
  );
}

// ─── Main view ─────────────────────────────────────────────────────────────────
export function AuditView() {
  const [actor,      setActor]      = useState('');
  const [action,     setAction]     = useState<'all' | AuditAction>('all');
  const [result,     setResult]     = useState<'all' | AuditResult>('all');
  const [resource,   setResource]   = useState('');
  const [fechaDesde, setFechaDesde] = useState('');
  const [fechaHasta, setFechaHasta] = useState('');
  const [applied, setApplied] = useState({
    actor: '', action: 'all' as 'all' | AuditAction,
    result: 'all' as 'all' | AuditResult,
    resource: '', fechaDesde: '', fechaHasta: '',
  });
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(10);
  const [detailLog, setDetailLog] = useState<AuditLog | null>(null);
  // Fuente real: GET /audit-logs (paginado server-side). Los filtros aplican
  // sobre la página traída porque el endpoint no expone filtros.
  const audit = useAuditLogs(page, perPage);

  const PER_PAGE_OPTIONS = [10, 25, 50];

  function aplicar() {
    setApplied({ actor, action, result, resource, fechaDesde, fechaHasta });
    setPage(1);
  }
  function limpiar() {
    setActor(''); setAction('all'); setResult('all'); setResource('');
    setFechaDesde(''); setFechaHasta('');
    setApplied({ actor: '', action: 'all', result: 'all', resource: '', fechaDesde: '', fechaHasta: '' });
    setPage(1);
  }

  const filteredLogs = useMemo(() => audit.logs.filter(log => {
    if (applied.actor  && !log.actor.toLowerCase().includes(applied.actor.toLowerCase())) return false;
    if (applied.action !== 'all' && log.action !== applied.action) return false;
    if (applied.result !== 'all' && log.result !== applied.result) return false;
    if (applied.resource && !log.resource.toLowerCase().includes(applied.resource.toLowerCase())) return false;
    if (applied.fechaDesde && log.timestamp < applied.fechaDesde) return false;
    if (applied.fechaHasta && log.timestamp > applied.fechaHasta + 'T23:59:59') return false;
    return true;
  }), [applied, audit.logs]);

  const totalLogs = audit.total;
  const totalPages = Math.max(1, Math.ceil(totalLogs / perPage));

  const totalSuccess = filteredLogs.filter(l => l.result === 'success').length;
  const totalFailure = filteredLogs.filter(l => l.result === 'failure').length;
  const actors       = new Set(audit.logs.map(l => l.actor)).size;

  return (
    <div>
      <h1 className="mb-1" style={{ fontSize: 22, fontWeight: 700 }}>Auditoría</h1>
      <p className="text-muted small mb-3">
        Registro de acciones realizadas por usuarios y el sistema. Backend real: GET /audit-logs?page&per_page
      </p>

      {(audit.isAuthBlocked || audit.isForbidden || audit.isConfigMissing) && !audit.isLoading && (
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-3 rounded-3 px-4 py-3 mb-4"
          style={{ background: '#FFF5E3', border: '1px solid #ffda6a', borderLeft: '4px solid #C47A00' }}>
          <p className="mb-0 small">
            <strong>No se pudo cargar la auditoría.</strong>{' '}
            {audit.isConfigMissing
              ? 'Falta configurar VITE_API_BASE_URL en el frontend.'
              : audit.isForbidden
                ? 'Acceso denegado: la auditoría requiere rol administrador o auditor.'
                : 'La API requiere autenticación Bearer. Inicie sesión nuevamente si su sesión expiró.'}
          </p>
          <button
            onClick={audit.retry}
            className="border-0 bg-transparent fw-semibold"
            style={{ fontSize: 13, color: '#965D00', cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            Reintentar
          </button>
        </div>
      )}

      {/* KPIs */}
      <div className="d-flex flex-wrap gap-3 mb-4">
        {[
          { label: 'Total de eventos',      value: totalLogs,     color: '#123B5D' },
          { label: 'Exitosos',              value: totalSuccess,  color: '#16835B' },
          { label: 'Fallidos',              value: totalFailure,  color: '#C83B3B' },
          { label: 'Actores con actividad', value: actors,        color: '#123B5D' },
        ].map(k => (
          <div key={k.label} className="cc-card d-flex align-items-center gap-3 px-3 py-2">
            <span style={{ fontSize: 26, fontWeight: 700, color: k.color }}>{k.value}</span>
            <span className="small text-muted">{k.label}</span>
          </div>
        ))}
      </div>

      {/* Filters */}
      <Card className="cc-card mb-4">
        <Card.Body>
          <div className="small fw-semibold text-muted text-uppercase mb-3" style={{ letterSpacing: '0.05em' }}>Filtros</div>
          <Row className="g-3 mb-3">
            <Col xs={12} sm={6} xl={3}>
              <Form.Label className="small fw-semibold text-muted">Actor (uuid)</Form.Label>
              <Form.Control size="sm" value={actor} onChange={e => setActor(e.target.value)} placeholder="uuid del actor…" />
            </Col>
            <Col xs={12} sm={6} xl={3}>
              <Form.Label className="small fw-semibold text-muted">Acción</Form.Label>
              <Form.Select size="sm" value={action} onChange={e => setAction(e.target.value as 'all' | AuditAction)}>
                <option value="all">Todas</option>
                {AUDIT_ACTIONS.map(a => <option key={a} value={a}>{a}</option>)}
              </Form.Select>
            </Col>
            <Col xs={12} sm={6} xl={2}>
              <Form.Label className="small fw-semibold text-muted">Resultado</Form.Label>
              <Form.Select size="sm" value={result} onChange={e => setResult(e.target.value as 'all' | AuditResult)}>
                <option value="all">Todos</option>
                <option value="success">success</option>
                <option value="failure">failure</option>
              </Form.Select>
            </Col>
            <Col xs={12} sm={6} xl={4}>
              <Form.Label className="small fw-semibold text-muted">Recurso (tipo/uuid)</Form.Label>
              <Form.Control size="sm" value={resource} onChange={e => setResource(e.target.value)} placeholder="ej. devices/d-001" />
            </Col>
          </Row>
          <Row className="g-3 mb-3">
            <Col xs={12} sm={6} xl={3}>
              <Form.Label className="small fw-semibold text-muted d-flex align-items-center gap-1">
                <Calendar size={11} />Rango de fechas
              </Form.Label>
              <div className="d-flex align-items-center gap-2">
                <div style={{ flex: 1, minWidth: 0 }}>
                  <CalendarPicker value={fechaDesde} onChange={setFechaDesde} placeholder="Desde" />
                </div>
                <span className="text-muted small flex-shrink-0">—</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <CalendarPicker value={fechaHasta} onChange={setFechaHasta} placeholder="Hasta" align="right" />
                </div>
              </div>
            </Col>
          </Row>
          <div className="d-flex gap-2">
            <Button variant="primary" size="sm" onClick={aplicar}>Aplicar filtros</Button>
            <Button variant="outline-secondary" size="sm" className="d-flex align-items-center gap-1" onClick={limpiar}>
              <X size={13} />Limpiar
            </Button>
          </div>
        </Card.Body>
      </Card>

      {/* Table */}
      <div className="cc-card overflow-hidden">
        <table className="w-100" style={{ borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#F5F8FA' }}>
              {['Fecha', 'Actor', 'Acción', 'Recurso', 'Resultado', ''].map(h => (
                <th key={h} className="px-4 py-3 text-start fw-semibold" style={{ color: '#52616B', fontSize: 12 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {audit.isLoading ? (
              <tr>
                <td colSpan={6} className="px-4 py-5 text-center text-muted">
                  Cargando registros…
                </td>
              </tr>
            ) : audit.status === 'error' ? (
              <tr>
                <td colSpan={6} className="px-4 py-5 text-center" style={{ color: '#B22F2F' }}>
                  No se pudieron cargar los registros. <button onClick={audit.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
                </td>
              </tr>
            ) : filteredLogs.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-5 text-center text-muted">
                  No se encontraron registros con los filtros aplicados.
                </td>
              </tr>
            ) : filteredLogs.map((log, i) => (
              <tr key={log.id} style={{ borderTop: '1px solid #EFF4F7', background: i % 2 === 1 ? '#FAFBFC' : '#fff' }}>
                <td className="px-4 py-3 text-muted font-monospace" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                  {formatTs(log.timestamp)}
                </td>
                <td className="px-4 py-3" style={{ fontSize: 12 }}>{log.actor}</td>
                <td className="px-4 py-3"><ActionBadge action={log.action} /></td>
                <td className="px-4 py-3"><ResourceBadge resource={log.resource} /></td>
                <td className="px-4 py-3"><ResultBadge result={log.result} /></td>
                <td className="px-4 py-3 text-end">
                  <button
                    className="border-0 bg-transparent p-1 rounded d-flex align-items-center justify-content-center"
                    style={{ cursor: 'pointer', color: '#1F6F8B' }}
                    onClick={() => setDetailLog(log)}
                    title="Ver detalle"
                  >
                    <Eye size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Pagination */}
        <div className="px-4 py-3 border-top d-flex flex-wrap align-items-center justify-content-between gap-2 small text-muted">
          <div>
            Mostrando {totalLogs === 0 ? 0 : (page - 1) * perPage + 1}–{Math.min(page * perPage, totalLogs)} de {totalLogs} registro{totalLogs !== 1 ? 's' : ''}
          </div>
          <div className="d-flex align-items-center gap-2">
            <span className="small text-muted">Por página:</span>
            <select
              className="form-select form-select-sm"
              style={{ width: 'auto', fontSize: 12 }}
              value={perPage}
              onChange={e => { setPerPage(Number(e.target.value)); setPage(1); }}
            >
              {PER_PAGE_OPTIONS.map(opt => <option key={opt} value={opt}>{opt}</option>)}
            </select>
            <div className="d-flex gap-1">
              <Button variant="outline-secondary" size="sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>
                <ChevronLeft size={13} />
              </Button>
              <span className="d-flex align-items-center px-2" style={{ fontSize: 12, color: '#52616B' }}>
                Página {page} de {totalPages}
              </span>
              <Button variant="outline-secondary" size="sm" disabled={page === totalPages} onClick={() => setPage(p => p + 1)}>
                <ChevronRight size={13} />
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Detail Modal */}
      <DetailModal log={detailLog} onClose={() => setDetailLog(null)} />
    </div>
  );
}