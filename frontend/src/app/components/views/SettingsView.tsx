import React, { useState } from 'react';
import { Bell, Thermometer, User, Save, RotateCcw, Info, Lock } from 'lucide-react';
import { Card, Form, Button, Row, Col } from '../../lib/bootstrap';

interface ToggleRowProps { checked: boolean; onChange: () => void; label: string; sub: string; id: string; }
function ToggleRow({ checked, onChange, label, sub, id }: ToggleRowProps) {
  return (
    <div className="d-flex justify-content-between align-items-center py-2" style={{ borderBottom: '1px solid #f0f0f0' }}>
      <div>
        <div className="fw-medium" style={{ fontSize: 14 }}>{label}</div>
        <div className="text-muted" style={{ fontSize: 12 }}>{sub}</div>
      </div>
      <Form.Check type="switch" id={id} checked={checked} onChange={onChange} className="ms-3" />
    </div>
  );
}

function SectionCard({ icon, iconColor, title, children }: { icon: React.ReactNode; iconColor?: string; title: string; children: React.ReactNode; }) {
  return (
    <Card className="cc-card mb-0">
      <div className="cc-card-header">
        <span style={{ color: iconColor }}>{icon}</span>
        {title}
      </div>
      <Card.Body>{children}</Card.Body>
    </Card>
  );
}

// ─── Read-only threshold row ──────────────────────────────────────────────────
function ThresholdRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="d-flex align-items-center gap-2 py-2" style={{ borderBottom: '1px solid #EFF4F7' }}>
      <span className="small text-muted" style={{ minWidth: 80 }}>{label}</span>
      <span className="font-monospace fw-bold" style={{ fontSize: 14, color: '#123B5D' }}>{value}</span>
    </div>
  );
}

export function SettingsView() {
  const [notifs, setNotifs] = useState({ dashboard: true, email: true, sms: false, push: false });

  const toggle = (key: keyof typeof notifs) => setNotifs(prev => ({ ...prev, [key]: !prev[key] }));

  return (
    <div>
      <h1 className="mb-1" style={{ fontSize: 20, fontWeight: 600 }}>Configuración del Sistema</h1>
      <p className="text-muted small mb-4">Ajustes y preferencias de la plataforma de monitoreo IoT.</p>

      <Row className="g-4">
        {/* User profile */}
        <Col xs={12} lg={6}>
          <SectionCard icon={<User size={16} />} iconColor="#123B5D" title="Perfil de Usuario">
            <Form>
              <Form.Group className="mb-3">
                <Form.Label className="small fw-semibold text-muted">Nombre completo</Form.Label>
                <Form.Control size="sm" type="text" defaultValue="Administrador del Sistema" />
              </Form.Group>
              <Form.Group className="mb-3">
                <Form.Label className="small fw-semibold text-muted">Correo electrónico</Form.Label>
                <Form.Control size="sm" type="email" defaultValue="admin@coldchain.iot" />
              </Form.Group>
              <Form.Group className="mb-3">
                <Form.Label className="small fw-semibold text-muted">Rol</Form.Label>
                <Form.Control size="sm" type="text" defaultValue="Administrador" readOnly
                  style={{ background: '#F5F8FA', color: '#52616B', cursor: 'default' }} />
                <Form.Text className="text-muted" style={{ fontSize: 11 }}>
                  El rol es asignado por el administrador del sistema.
                </Form.Text>
              </Form.Group>
              <Form.Group>
                <Form.Label className="small fw-semibold text-muted">Organización</Form.Label>
                <Form.Control size="sm" type="text" defaultValue="Proyecto IoT — Cadena de Frío" />
              </Form.Group>
            </Form>
          </SectionCard>
        </Col>

        {/* Notifications channels */}
        <Col xs={12} lg={6}>
          <SectionCard icon={<Bell size={16} />} iconColor="#1F6F8B" title="Canales de Notificación">
            <p className="text-muted small mb-3">
              Activar o desactivar los canales por los que desea recibir notificaciones de alertas.
            </p>
            <ToggleRow id="notif-dashboard" checked={notifs.dashboard} onChange={() => toggle('dashboard')} label="Dashboard"  sub="Notificaciones en la interfaz web" />
            <ToggleRow id="notif-email"     checked={notifs.email}     onChange={() => toggle('email')}     label="Email"      sub="Notificaciones por correo electrónico" />
            <ToggleRow id="notif-sms"       checked={notifs.sms}       onChange={() => toggle('sms')}       label="SMS"        sub="Notificaciones por mensaje de texto" />
            <ToggleRow id="notif-push"      checked={notifs.push}      onChange={() => toggle('push')}      label="Push"       sub="Notificaciones push en dispositivo móvil" />
          </SectionCard>
        </Col>

        {/* Thresholds — read only */}
        <Col xs={12}>
          <SectionCard icon={<Thermometer size={16} />} iconColor="#C47A00" title="Umbrales actuales">
            {/* Read-only notice */}
            <div className="d-flex align-items-start gap-2 rounded-3 px-3 py-2 mb-4"
              style={{ background: '#E8F5F6', border: '1px solid #27B3C2' }}>
              <Lock size={14} style={{ color: '#1F6F8B', flexShrink: 0, marginTop: 2 }} />
              <div>
                <span className="fw-semibold small" style={{ color: '#123B5D' }}>Configuración informativa — solo lectura</span>
                <p className="text-muted mb-0" style={{ fontSize: 12 }}>
                  Los umbrales son definidos en el backend del sistema. No son editables desde la interfaz.
                </p>
              </div>
            </div>
            <Row className="g-4">
              <Col xs={12} sm={4}>
                <div className="small fw-semibold text-muted text-uppercase mb-2" style={{ letterSpacing: '0.06em', fontSize: 11 }}>
                  Temperatura
                </div>
                <ThresholdRow label="Mínimo" value="0 °C" />
                <ThresholdRow label="Máximo" value="4 °C" />
              </Col>
              <Col xs={12} sm={4}>
                <div className="small fw-semibold text-muted text-uppercase mb-2" style={{ letterSpacing: '0.06em', fontSize: 11 }}>
                  Humedad
                </div>
                <ThresholdRow label="Mínimo" value="85 %" />
                <ThresholdRow label="Máximo" value="90 %" />
              </Col>
              <Col xs={12} sm={4}>
                <div className="small fw-semibold text-muted text-uppercase mb-2" style={{ letterSpacing: '0.06em', fontSize: 11 }}>
                  Energía
                </div>
                <ThresholdRow label="Estado esperado" value="ON" />
                <p className="text-muted mt-2 mb-0" style={{ fontSize: 11 }}>
                  Se genera alerta cuando el estado es OFF.
                </p>
              </Col>
            </Row>

            {/* Info footer */}
            <div className="d-flex align-items-center gap-2 mt-3 pt-3" style={{ borderTop: '1px dashed #D9E2E8' }}>
              <Info size={13} style={{ color: '#52616B', flexShrink: 0 }} />
              <p className="text-muted mb-0" style={{ fontSize: 12 }}>
                Los umbrales son globales para todos los dispositivos y no se pueden configurar por dispositivo.
              </p>
            </div>
          </SectionCard>
        </Col>
      </Row>

      <div className="d-flex justify-content-end gap-2 mt-4">
        <Button variant="outline-secondary" className="d-flex align-items-center gap-2">
          <RotateCcw size={14} />Cancelar
        </Button>
        <Button variant="primary" className="d-flex align-items-center gap-2">
          <Save size={14} />Guardar preferencias
        </Button>
      </div>
    </div>
  );
}
