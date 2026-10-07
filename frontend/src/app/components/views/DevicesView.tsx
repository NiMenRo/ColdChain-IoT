import { useState, useEffect } from 'react';
import {
  Thermometer, Droplets, Zap, ChevronDown, ChevronUp,
  Snowflake, AlertTriangle, WrenchIcon, PowerOff,
  Plus, Edit2, X, Save, Settings,
} from 'lucide-react';
import { Button, Form, Row, Col } from '../../lib/bootstrap';
import {
  useDevices, Device, DeviceStatus, DeviceType, SensorType,
  DEVICE_TYPE_LABEL, SENSOR_LABEL, DeviceFormData,
} from '../../contexts/DeviceContext';
import type { DeviceReadingSnapshot, DeviceSensor } from '../../types/devices';
import { useAuth } from '../../hooks/useAuth';
import { hasActionPermission } from '../../config/rbac';

// ─── Status config ────────────────────────────────────────────────────────────
const STATUS_CONFIG: Record<DeviceStatus, { label: string; bg: string; color: string; border: string; Icon: React.ElementType }> = {
  active:      { label: 'Activo',        bg: '#EAF6EF', color: '#16835B', border: '#a3cfbb', Icon: Snowflake     },
  inactive:    { label: 'Inactivo',      bg: '#EFF4F7', color: '#52616B', border: '#D9E2E8', Icon: PowerOff      },
  maintenance: { label: 'Mantenimiento', bg: '#FFF5E3', color: '#965D00', border: '#ffda6a', Icon: WrenchIcon    },
  error:       { label: 'Error',         bg: '#FCEEEE', color: '#B22F2F', border: '#f1aeb5', Icon: AlertTriangle },
};

const ALL_SENSORS: SensorType[] = ['temperature', 'humidity', 'energy'];

// ─── History mock ──────────────────────────────────────────────────────────────
const HISTORY_MOCK: Record<string, { ts: string; temperature: number | null; humidity: number | null; energy: 'on' | 'off' }[]> = {
  'DEV-001': [
    { ts: '10:41', temperature: 2.1, humidity: 86, energy: 'on' },
    { ts: '10:31', temperature: 2.3, humidity: 85, energy: 'on' },
    { ts: '10:21', temperature: 2.0, humidity: 87, energy: 'on' },
    { ts: '10:11', temperature: 1.9, humidity: 86, energy: 'on' },
    { ts: '10:01', temperature: 2.2, humidity: 85, energy: 'on' },
  ],
  'DEV-002': [
    { ts: '10:40', temperature: 3.4, humidity: 88, energy: 'on' },
    { ts: '10:30', temperature: 3.6, humidity: 89, energy: 'on' },
    { ts: '10:20', temperature: 3.8, humidity: 88, energy: 'on' },
    { ts: '10:10', temperature: 4.1, humidity: 90, energy: 'on' },
    { ts: '10:00', temperature: 3.9, humidity: 88, energy: 'on' },
  ],
  'DEV-003': [
    { ts: '10:38', temperature: 6.8, humidity: 92, energy: 'on' },
    { ts: '10:28', temperature: 6.2, humidity: 91, energy: 'on' },
    { ts: '10:18', temperature: 5.9, humidity: 90, energy: 'on' },
    { ts: '10:08', temperature: 5.4, humidity: 89, energy: 'on' },
    { ts: '09:58', temperature: 4.9, humidity: 88, energy: 'on' },
  ],
  'DEV-005': [
    { ts: '10:41', temperature: 1.9, humidity: 87, energy: 'on' },
    { ts: '10:31', temperature: 2.1, humidity: 87, energy: 'on' },
    { ts: '10:21', temperature: 2.0, humidity: 86, energy: 'on' },
    { ts: '10:11', temperature: 1.8, humidity: 87, energy: 'on' },
    { ts: '10:01', temperature: 1.9, humidity: 86, energy: 'on' },
  ],
};

// ─── Overlay Modal ─────────────────────────────────────────────────────────────
function Modal({ show, onHide, title, children }: {
  show: boolean; onHide: () => void; title: string; children: React.ReactNode;
}) {
  useEffect(() => {
    document.body.style.overflow = show ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [show]);

  if (!show) return null;
  return (
    <div onClick={onHide}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1050,
               display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div onClick={e => e.stopPropagation()}
        style={{ background: '#fff', borderRadius: 12, width: '100%', maxWidth: 540,
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

// ─── Sensor Config Form ────────────────────────────────────────────────────────
function SensorConfigForm({ device, currentSensors, onSave, onCancel }: {
  device: Device;
  currentSensors: SensorType[];
  onSave: (sensors: SensorType[]) => void;
  onCancel: () => void;
}) {
  const [enabled, setEnabled] = useState<SensorType[]>(currentSensors);
  const [error, setError] = useState('');

  function toggleSensor(s: SensorType) {
    setEnabled(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]);
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (enabled.length === 0) {
      setError('El dispositivo debe tener al menos un sensor configurado.');
      return;
    }
    onSave(enabled);
  }

  return (
    <form onSubmit={submit} noValidate>
      <p className="text-muted small mb-3">
        Configura el conjunto completo de sensores para <strong>{device.name}</strong>.
        Esta operación reemplaza la configuración actual (PUT /devices/{'{id}'}/sensors).
      </p>
      <div className="small fw-semibold text-muted mb-1">Sensores</div>
      <div className="rounded-3 p-3 mb-3" style={{ background: '#F5F8FA', border: '1px solid #E4ECF1' }}>
        <div className="d-flex flex-wrap gap-3">
          {ALL_SENSORS.map(s => {
            const checked = enabled.includes(s);
            return (
              <label key={s} className="d-flex align-items-center gap-2 small"
                style={{ cursor: 'pointer', userSelect: 'none' }}>
                <input type="checkbox" className="form-check-input m-0" checked={checked}
                  onChange={() => toggleSensor(s)}
                  style={{ width: 16, height: 16, accentColor: '#123B5D', cursor: 'pointer' }} />
                <span style={{ color: checked ? '#123B5D' : '#52616B', fontWeight: checked ? 600 : 400 }}>
                  {SENSOR_LABEL[s]}
                </span>
              </label>
            );
          })}
        </div>
        {error && <div className="small mt-2" style={{ color: '#C83B3B' }}>{error}</div>}
      </div>
      <div className="d-flex gap-2 justify-content-end">
        <Button type="button" variant="outline-secondary" size="sm" onClick={onCancel}>Cancelar</Button>
        <Button type="submit" variant="primary" size="sm" className="d-flex align-items-center gap-1">
          <Save size={13} />Guardar configuración
        </Button>
      </div>
    </form>
  );
}

// ─── Device Form ───────────────────────────────────────────────────────────────
function DeviceForm({ initial, onSave, onCancel }: {
  initial: DeviceFormData;
  onSave: (data: DeviceFormData) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<DeviceFormData>(initial);
  const [errors, setErrors] = useState<{ code?: string; name?: string; location?: string; sensors?: string }>({});

  function toggleSensor(s: SensorType) {
    setForm(prev => ({
      ...prev,
      sensors: prev.sensors.includes(s)
        ? prev.sensors.filter(x => x !== s)
        : [...prev.sensors, s],
    }));
  }

  function validate() {
    const e: typeof errors = {};
    if (!form.code.trim())           e.code    = 'El código es requerido.';
    if (!form.name.trim())           e.name    = 'El nombre es requerido.';
    if (!form.location.trim())       e.location = 'La ubicación es requerida.';
    if (form.sensors.length === 0)   e.sensors = 'Selecciona al menos un sensor.';
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (validate()) onSave(form);
  }

  return (
    <form onSubmit={submit} noValidate>
      <Row className="g-3 mb-3">
        <Col xs={12}>
          <Form.Label className="small fw-semibold text-muted">Código</Form.Label>
          <Form.Control size="sm" value={form.code} placeholder="Ej. CAVA-NTE"
            onChange={e => setForm(p => ({ ...p, code: e.target.value }))}
            isInvalid={!!errors.code} />
          {errors.code && <div className="invalid-feedback d-block" style={{ fontSize: 12 }}>{errors.code}</div>}
        </Col>
        <Col xs={12}>
          <Form.Label className="small fw-semibold text-muted">Nombre del dispositivo</Form.Label>
          <Form.Control size="sm" value={form.name} placeholder="Ej. Cava Norte"
            onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
            isInvalid={!!errors.name} />
          {errors.name && <div className="invalid-feedback d-block" style={{ fontSize: 12 }}>{errors.name}</div>}
        </Col>
        <Col xs={12} sm={6}>
          <Form.Label className="small fw-semibold text-muted">Tipo</Form.Label>
          <Form.Select size="sm" value={form.device_type}
            onChange={e => setForm(p => ({ ...p, device_type: e.target.value as DeviceType }))}>
            <option value="cold_room">Cava (cold_room)</option>
            <option value="refrigerated_showcase">Vitrina (refrigerated_showcase)</option>
          </Form.Select>
        </Col>
        <Col xs={12} sm={6}>
          <Form.Label className="small fw-semibold text-muted">Estado inicial</Form.Label>
          <Form.Select size="sm" value={form.status}
            onChange={e => setForm(p => ({ ...p, status: e.target.value as DeviceStatus }))}>
            {(Object.keys(STATUS_CONFIG) as DeviceStatus[]).map(s => (
              <option key={s} value={s}>{STATUS_CONFIG[s].label}</option>
            ))}
          </Form.Select>
        </Col>
        <Col xs={12}>
          <Form.Label className="small fw-semibold text-muted">Ubicación</Form.Label>
          <Form.Control size="sm" value={form.location} placeholder="Ej. Zona A"
            onChange={e => setForm(p => ({ ...p, location: e.target.value }))}
            isInvalid={!!errors.location} />
          {errors.location && <div className="invalid-feedback d-block" style={{ fontSize: 12 }}>{errors.location}</div>}
        </Col>
      </Row>

      {/* Sensor selection */}
      <div className="small fw-semibold text-muted mb-1">Sensores</div>
      <div className="rounded-3 p-3 mb-1" style={{ background: '#F5F8FA', border: '1px solid #E4ECF1' }}>
        <div className="d-flex flex-wrap gap-3">
          {ALL_SENSORS.map(s => {
            const checked = form.sensors.includes(s);
            return (
              <label key={s} className="d-flex align-items-center gap-2 small"
                style={{ cursor: 'pointer', userSelect: 'none' }}>
                <input type="checkbox" className="form-check-input m-0" checked={checked}
                  onChange={() => toggleSensor(s)}
                  style={{ width: 16, height: 16, accentColor: '#123B5D', cursor: 'pointer' }} />
                <span style={{ color: checked ? '#123B5D' : '#52616B', fontWeight: checked ? 600 : 400 }}>
                  {SENSOR_LABEL[s]}
                </span>
              </label>
            );
          })}
        </div>
        {errors.sensors && (
          <div className="small mt-2" style={{ color: '#C83B3B' }}>{errors.sensors}</div>
        )}
      </div>
      <p className="text-muted mb-4" style={{ fontSize: 11 }}>
        Los sensores representan los tipos de lectura que el dispositivo reporta al sistema.
      </p>

      <div className="d-flex gap-2 justify-content-end">
        <Button type="button" variant="outline-secondary" size="sm" onClick={onCancel}>Cancelar</Button>
        <Button type="submit" variant="primary" size="sm" className="d-flex align-items-center gap-1">
          <Save size={13} />Guardar
        </Button>
      </div>
    </form>
  );
}

// ─── Reading history detail ────────────────────────────────────────────────────
function ReadingRow({ device }: { device: Device }) {
  const history = HISTORY_MOCK[device.id] ?? [];
  const temps = history.filter(h => h.temperature !== null).map(h => h.temperature as number);
  const hums  = history.filter(h => h.humidity    !== null).map(h => h.humidity    as number);
  const stats = temps.length > 0 ? {
    tempAvg: (temps.reduce((a, b) => a + b, 0) / temps.length).toFixed(1),
    tempMin: Math.min(...temps).toFixed(1), tempMax: Math.max(...temps).toFixed(1),
    humAvg:  (hums.reduce((a, b) => a + b, 0)  / hums.length).toFixed(0),
    humMin:  Math.min(...hums).toFixed(0),  humMax: Math.max(...hums).toFixed(0),
  } : null;

  return (
    <div className="mt-3">
      <div className="small fw-semibold text-muted text-uppercase mb-2"
        style={{ letterSpacing: '0.06em', fontSize: 11 }}>Últimas lecturas</div>
      <div className="overflow-auto">
        <table className="w-100" style={{ fontSize: 12, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ color: '#52616B' }}>
              <th className="py-1 pe-4 text-start fw-medium">Hora</th>
              <th className="py-1 pe-4 text-start fw-medium">Temperatura</th>
              <th className="py-1 pe-4 text-start fw-medium">Humedad</th>
              <th className="py-1 text-start fw-medium">Energía</th>
            </tr>
          </thead>
          <tbody>
            {history.length === 0
              ? <tr><td colSpan={4} className="py-2 text-muted">Sin lecturas disponibles.</td></tr>
              : history.map((h, i) => (
                <tr key={i} style={{ borderTop: '1px solid #EFF4F7' }}>
                  <td className="py-1 pe-4 font-monospace text-muted">{h.ts}</td>
                  <td className="py-1 pe-4 fw-medium">
                    {h.temperature !== null
                      ? <span style={{ color: h.temperature > 4 ? '#C83B3B' : '#123B5D' }}>{h.temperature} °C</span>
                      : '—'}
                  </td>
                  <td className="py-1 pe-4 fw-medium">
                    {h.humidity !== null
                      ? <span style={{ color: h.humidity > 90 ? '#C83B3B' : '#123B5D' }}>{h.humidity} %</span>
                      : '—'}
                  </td>
                  <td className="py-1">
                    <span className="fw-semibold" style={{ color: h.energy === 'on' ? '#16835B' : '#C83B3B' }}>
                      {h.energy === 'on' ? 'ON' : 'OFF'}
                    </span>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      {stats && (
        <div className="d-flex flex-wrap gap-4 mt-3 pt-3" style={{ borderTop: '1px dashed #D9E2E8' }}>
          <div>
            <div className="small text-muted mb-1">Temperatura (prom / mín / máx)</div>
            <span className="fw-semibold small">{stats.tempAvg} °C</span>
            <span className="text-muted small"> / {stats.tempMin} / {stats.tempMax} °C</span>
          </div>
          <div>
            <div className="small text-muted mb-1">Humedad (prom / mín / máx)</div>
            <span className="fw-semibold small">{stats.humAvg} %</span>
            <span className="text-muted small"> / {stats.humMin} / {stats.humMax} %</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Device Card ───────────────────────────────────────────────────────────────
function DeviceCard({ device, reading, sensors: deviceSensors, canManage, onConfigure }: {
  device: Device;
  reading: DeviceReadingSnapshot | undefined;
  sensors: DeviceSensor[];
  canManage: boolean;
  onConfigure: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const s = STATUS_CONFIG[device.status];
  const Icon = s.Icon;
  const tempCritical = reading?.temperature !== null && reading?.temperature !== undefined && reading.temperature > 4;
  const humCritical  = reading?.humidity    !== null && reading?.humidity    !== undefined && reading.humidity    > 90;

  return (
    <div className="rounded-3 overflow-hidden" style={{ border: `1px solid ${s.border}` }}>
      <div className="p-3" style={{ background: s.bg }}>
        <div className="d-flex justify-content-between align-items-start gap-2">
          <div className="d-flex align-items-center gap-2">
            <div className="rounded-2 p-1" style={{ background: '#fff', color: s.color }}>
              <Icon size={16} />
            </div>
            <div>
              <div className="fw-semibold" style={{ fontSize: 14 }}>{device.name}</div>
              <div className="text-muted" style={{ fontSize: 11 }}>{device.code} · {device.location}</div>
            </div>
          </div>
          <div className="d-flex align-items-center gap-2 flex-shrink-0">
            <span className="fw-semibold rounded-pill px-2 py-0"
              style={{ fontSize: 11, color: s.color, background: '#fff', border: `1px solid ${s.border}` }}>
              {s.label}
            </span>
            {canManage && (
              <button onClick={onConfigure}
                className="border-0 rounded p-1 d-flex align-items-center justify-content-center"
                style={{ background: '#fff', cursor: 'pointer', color: '#1F6F8B' }} title="Configurar sensores">
                <Settings size={13} />
              </button>
            )}
          </div>
        </div>

        <div className="d-flex flex-wrap gap-1 mt-2">
          <span className="rounded-pill px-2 py-0"
            style={{ fontSize: 11, background: '#fff', color: '#52616B', border: '1px solid #D9E2E8' }}>
            {DEVICE_TYPE_LABEL[device.device_type]}
          </span>
          {deviceSensors.map(sensor => (
            <span key={sensor.sensor_type} className="rounded-pill px-2 py-0"
              style={{ fontSize: 11, background: '#EAF1F5', color: '#123B5D', border: '1px solid #c5d9e6' }}>
              {SENSOR_LABEL[sensor.sensor_type]}
            </span>
          ))}
        </div>
      </div>

      <div className="p-3" style={{ background: '#fff' }}>
        {device.status === 'active' && reading && reading.temperature !== null ? (
          <div className="d-flex flex-wrap gap-3">
            {deviceSensors.some(s => s.sensor_type === 'temperature') && (
              <div className="d-flex align-items-center gap-2">
                <Thermometer size={15} style={{ color: tempCritical ? '#C83B3B' : '#1F6F8B', flexShrink: 0 }} />
                <div>
                  <div className="text-muted" style={{ fontSize: 11 }}>Temperatura</div>
                  <div className="fw-bold" style={{ color: tempCritical ? '#C83B3B' : '#17232D' }}>{reading.temperature} °C</div>
                </div>
              </div>
            )}
            {deviceSensors.some(s => s.sensor_type === 'humidity') && reading.humidity !== null && (
              <div className="d-flex align-items-center gap-2">
                <Droplets size={15} style={{ color: humCritical ? '#C83B3B' : '#1F6F8B', flexShrink: 0 }} />
                <div>
                  <div className="text-muted" style={{ fontSize: 11 }}>Humedad</div>
                  <div className="fw-bold" style={{ color: humCritical ? '#C83B3B' : '#17232D' }}>{reading.humidity} %</div>
                </div>
              </div>
            )}
            {deviceSensors.some(s => s.sensor_type === 'energy') && (
              <div className="d-flex align-items-center gap-2">
                <Zap size={15} style={{ color: reading.energy === 'on' ? '#16835B' : '#C83B3B', flexShrink: 0 }} />
                <div>
                  <div className="text-muted" style={{ fontSize: 11 }}>Energía</div>
                  <div className="fw-bold" style={{ color: reading.energy === 'on' ? '#16835B' : '#C83B3B' }}>
                    {reading.energy === 'on' ? 'ON' : 'OFF'}
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-muted small mb-0">
            {device.status === 'maintenance' ? 'Dispositivo en mantenimiento — sin lecturas disponibles.'
             : device.status === 'inactive'  ? 'Dispositivo inactivo.'
             : device.status === 'error'     ? 'Dispositivo en error.'
             : 'Sin lecturas disponibles.'}
          </p>
        )}

        <div className="d-flex justify-content-between align-items-center mt-3">
          <span className="text-muted" style={{ fontSize: 11 }}>
            {reading?.timestamp && (
              <>Última lectura: <span className="font-monospace">{new Date(reading.timestamp).toLocaleString('es-CO', {
                day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
              })}</span></>
            )}
          </span>
          <button onClick={() => setExpanded(!expanded)}
            className="d-flex align-items-center gap-1 border-0 bg-transparent fw-medium"
            style={{ fontSize: 12, color: '#1F6F8B', cursor: 'pointer' }}>
            {expanded ? <><ChevronUp size={14} />Ocultar historial</> : <><ChevronDown size={14} />Ver historial</>}
          </button>
        </div>
        {expanded && <ReadingRow device={device} />}
      </div>
    </div>
  );
}

// ─── Main view ─────────────────────────────────────────────────────────────────
type FilterStatus = 'all' | DeviceStatus;
type FilterType   = 'all' | DeviceType;

export function DevicesView() {
  const { devices, sensors, addDevice, replaceSensors, getSensors, getReading } = useDevices();
  const { role } = useAuth();
  const canManage = hasActionPermission(role, 'manageDevices');

  const [filterStatus, setFilterStatus] = useState<FilterStatus>('all');
  const [filterType,   setFilterType]   = useState<FilterType>('all');

  const [createModal, setCreateModal] = useState(false);
  const [sensorConfigDevice, setSensorConfigDevice] = useState<Device | null>(null);

  const counts = {
    active:      devices.filter(d => d.status === 'active').length,
    maintenance: devices.filter(d => d.status === 'maintenance').length,
    error:       devices.filter(d => d.status === 'error').length,
    inactive:    devices.filter(d => d.status === 'inactive').length,
  };

  const filtered = devices.filter(d =>
    (filterStatus === 'all' || d.status === filterStatus) &&
    (filterType   === 'all' || d.device_type === filterType)
  );

  function openCreate() { setCreateModal(true); }
  function closeCreate() { setCreateModal(false); }

  function handleSaveNew(data: DeviceFormData) {
    const result = addDevice(data);
    if (result.ok) {
      closeCreate();
    } else {
      alert(result.error ?? 'Error al crear el dispositivo.');
    }
  }

  function handleSaveSensors(deviceId: string, sensorTypes: SensorType[]) {
    const result = replaceSensors(deviceId, sensorTypes);
    if (result.ok) {
      setSensorConfigDevice(null);
    } else {
      alert(result.error ?? 'Error al actualizar sensores.');
    }
  }

  const createModalInitial: DeviceFormData = {
    code: '', name: '', location: '', device_type: 'cold_room', status: 'active',
    sensors: ['temperature', 'humidity', 'energy'],
  };

  return (
    <div>
      <div className="d-flex justify-content-between align-items-start mb-1 flex-wrap gap-2">
        <div>
          <h1 className="mb-1" style={{ fontSize: 22, fontWeight: 700 }}>Dispositivos</h1>
          <p className="text-muted small mb-0">Monitoreo de cavas y vitrinas en tiempo real.</p>
        </div>
        {canManage && (
          <Button variant="primary" size="sm" className="d-flex align-items-center gap-2" onClick={openCreate}>
            <Plus size={15} />Nuevo dispositivo
          </Button>
        )}
      </div>

      {canManage && (
        <div className="d-flex align-items-center gap-2 mt-2 mb-4 rounded-3 px-3 py-2"
          style={{ background: '#EAF1F5', border: '1px solid #c5d9e6', fontSize: 12, color: '#1F6F8B' }}>
          <Edit2 size={12} style={{ flexShrink: 0 }} />
          Modo gestión activo — puedes crear dispositivos y configurar sensores (solo admin).
        </div>
      )}
      {!canManage && <div className="mb-4" />}

      {/* Summary strip */}
      <div className="d-flex flex-wrap gap-3 mb-4">
        {[
          { label: 'Activos',       value: counts.active,      color: '#16835B', bg: '#EAF6EF', border: '#a3cfbb' },
          { label: 'Mantenimiento', value: counts.maintenance, color: '#965D00', bg: '#FFF5E3', border: '#ffda6a' },
          { label: 'Error',         value: counts.error,       color: '#B22F2F', bg: '#FCEEEE', border: '#f1aeb5' },
          { label: 'Inactivos',     value: counts.inactive,    color: '#52616B', bg: '#EFF4F7', border: '#D9E2E8' },
        ].map(s => (
          <div key={s.label} className="d-flex align-items-center gap-2 rounded-3 px-3 py-2"
            style={{ background: s.bg, border: `1px solid ${s.border}` }}>
            <span style={{ fontSize: 22, fontWeight: 700, color: s.color }}>{s.value}</span>
            <span style={{ fontSize: 13, color: s.color }}>{s.label}</span>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="d-flex flex-wrap gap-3 mb-4">
        <div className="d-flex align-items-center gap-2 flex-wrap">
          <span className="small fw-semibold text-muted">Estado:</span>
          {(['all', 'active', 'inactive', 'maintenance', 'error'] as FilterStatus[]).map(s => (
            <button key={s} onClick={() => setFilterStatus(s)} className="rounded-2 border px-3 py-1"
              style={{ fontSize: 12, cursor: 'pointer', fontWeight: filterStatus === s ? 600 : 400,
                background:  filterStatus === s ? '#123B5D' : '#fff',
                color:       filterStatus === s ? '#fff'    : '#52616B',
                borderColor: filterStatus === s ? '#123B5D' : '#D9E2E8' }}>
              {s === 'all' ? 'Todos' : STATUS_CONFIG[s].label}
            </button>
          ))}
        </div>
        <div className="d-flex align-items-center gap-2 flex-wrap">
          <span className="small fw-semibold text-muted">Tipo:</span>
          {(['all', 'cold_room', 'refrigerated_showcase'] as FilterType[]).map(t => (
            <button key={t} onClick={() => setFilterType(t)} className="rounded-2 border px-3 py-1"
              style={{ fontSize: 12, cursor: 'pointer', fontWeight: filterType === t ? 600 : 400,
                background:  filterType === t ? '#1F6F8B' : '#fff',
                color:       filterType === t ? '#fff'    : '#52616B',
                borderColor: filterType === t ? '#1F6F8B' : '#D9E2E8' }}>
              {t === 'all' ? 'Todos' : DEVICE_TYPE_LABEL[t]}
            </button>
          ))}
        </div>
      </div>

      {/* Device cards */}
      {filtered.length === 0 ? (
        <div className="cc-card p-5 text-center">
          <p className="text-muted mb-0">No hay dispositivos que coincidan con los filtros seleccionados.</p>
        </div>
      ) : (
        <div className="row g-3">
          {filtered.map(d => {
            const reading = getReading(d.id);
            const deviceSensors = sensors.filter(s => s.device_id === d.id);
            return (
              <div key={d.id} className="col-12 col-lg-6">
                <DeviceCard
                  device={d}
                  reading={reading}
                  sensors={deviceSensors}
                  canManage={canManage}
                  onConfigure={() => setSensorConfigDevice(d)}
                />
              </div>
            );
          })}
        </div>
      )}

      <p className="text-muted mt-3 mb-0" style={{ fontSize: 11 }}>
        {filtered.length} de {devices.length} dispositivo{devices.length !== 1 ? 's' : ''} mostrado{filtered.length !== 1 ? 's' : ''}.
      </p>

      {/* Create modal */}
      <Modal show={createModal} onHide={closeCreate} title="Nuevo dispositivo">
        <DeviceForm initial={createModalInitial} onSave={handleSaveNew} onCancel={closeCreate} />
      </Modal>

      {/* Sensor config modal */}
      <Modal show={!!sensorConfigDevice} onHide={() => setSensorConfigDevice(null)}
        title={sensorConfigDevice ? `Configurar sensores — ${sensorConfigDevice.name}` : ''}>
        {sensorConfigDevice && (
          <SensorConfigForm
            device={sensorConfigDevice}
            currentSensors={getSensors(sensorConfigDevice.id) as SensorType[]}
            onSave={(sensors) => handleSaveSensors(sensorConfigDevice.id, sensors)}
            onCancel={() => setSensorConfigDevice(null)}
          />
        )}
      </Modal>
    </div>
  );
}
