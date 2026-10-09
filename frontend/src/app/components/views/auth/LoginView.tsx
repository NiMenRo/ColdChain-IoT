import { useState, useRef } from 'react';
import { Navigate, useNavigate, useLocation } from 'react-router';
import {
  Eye, EyeOff, Snowflake, ArrowRight, Thermometer, Droplets, Zap,
  LoaderCircle, AlertCircle, Mail, Lock, ChevronDown, Globe,
} from 'lucide-react';
import { useAuth } from '../../../hooks/useAuth';
import { useDevices, Device } from '../../../contexts/DeviceContext';

// ─── Demo roles ────────────────────────────────────────────────────────────────
const DEMO_ROLES = [
  { id: 'admin',      label: 'Administrador', desc: 'Acceso completo'   },
  { id: 'supervisor', label: 'Supervisor',    desc: 'Gestión y alertas' },
  { id: 'operador',   label: 'Operador',      desc: 'Monitoreo activo'  },
  { id: 'auditor',    label: 'Auditor',       desc: 'Solo lectura'      },
];

// ─── Sparkline determinista centrada en un valor base ─────────────────────────
const OFFSETS = [0.2, -0.1, 0.3, -0.2, 0.1, 0.0, -0.1, 0.2, -0.3, 0.1,
                 0.2, -0.1, 0.0, 0.3, -0.2, 0.1, -0.1, 0.2, 0.0, -0.2,
                 0.1,  0.3, -0.1, 0.0];

function TempSparkline({ base }: { base: number }) {
  const temps = OFFSETS.map(o => base + o);
  const min   = Math.min(...temps) - 0.5;
  const max   = Math.max(...temps) + 0.5;
  const W = 400, H = 72;
  const y = (t: number) => ((max - t) / (max - min)) * H;
  const x = (i: number) => (i / (temps.length - 1)) * W;
  const line = temps.map((t, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(t).toFixed(1)}`).join(' ');
  const area = `${line} L${W},${H} L0,${H} Z`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none"
      style={{ width: '100%', height: 72, display: 'block' }} aria-hidden="true">
      <defs>
        <linearGradient id="cc-spark" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#27B3C2" stopOpacity="0.35" />
          <stop offset="1" stopColor="#27B3C2" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#cc-spark)" />
      <path d={line} fill="none" stroke="#5FD3DF" strokeWidth="2"
        vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  );
}

// ─── Brand mark ────────────────────────────────────────────────────────────────
function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <div style={{
        width: compact ? 36 : 42, height: compact ? 36 : 42, borderRadius: 10,
        background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.16)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Snowflake size={compact ? 20 : 24} color="#7EDBE4" strokeWidth={1.8} />
      </div>
      <div>
        <div style={{ fontSize: compact ? 16 : 18, fontWeight: 700, color: '#fff', letterSpacing: '-0.01em' }}>
          ColdChain<span style={{ color: '#7EDBE4', fontWeight: 500 }}>-IoT</span>
        </div>
        {!compact && (
          <div className="cc-eyebrow" style={{ color: 'var(--cc-ink-inv-3)', marginTop: 1 }}>
            Plataforma de monitoreo
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Glass card with real device data ─────────────────────────────────────────
function DeviceLiveCard({ devices }: { devices: Device[] }) {
  const { getSensors, getReading } = useDevices();
  const featured = devices.find(d => d.status === 'active') ?? null;
  const activeCount = devices.filter(d => d.status === 'active').length;
  const errorCount  = devices.filter(d => d.status === 'error').length;
  const featuredSensors = featured ? getSensors(featured.id) : [];
  const featuredReading = featured ? getReading(featured.id) : null;
  const activeTemps = devices
    .filter(d => d.status === 'active')
    .map(d => getReading(d.id)?.temperature ?? null)
    .filter((t): t is number => t !== null);
  const avgTemp = activeTemps.length > 0
    ? (activeTemps.reduce((a, b) => a + b, 0) / activeTemps.length).toFixed(1)
    : null;

  // KPI tiles derived from real data
  const kpis = [
    {
      num: devices.length === 0 ? '—' : String(activeCount),
      lbl: 'Dispositivos activos',
    },
    {
      num: avgTemp !== null ? `${avgTemp} °C` : '—',
      lbl: 'Temperatura promedio',
    },
    {
      num: devices.length === 0 ? '—' : String(errorCount),
      lbl: 'Con error',
    },
  ];

  return (
    <>
      {/* Live device card */}
      <div className="cc-glass" style={{ padding: '20px 22px' }}>
        {featured ? (
          <>
            {/* Card header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
              <div style={{ width: 38, height: 38, borderRadius: 9, background: 'rgba(95,211,223,0.16)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Snowflake size={20} color="#7EDBE4" strokeWidth={1.7} />
              </div>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#fff' }}>
                  {featured.name} · {featured.location}
                </div>
                <div style={{ fontSize: 12, color: 'var(--cc-ink-inv-3)', marginTop: 2 }}>
                  {featured.id} · última lectura reciente
                </div>
              </div>
              <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 7 }}>
                <span className="cc-dot" />
                <span style={{ fontSize: 12, color: '#8BE3B5', fontWeight: 600 }}>Activo</span>
              </div>
            </div>

            {/* Sparkline — centrada en la temperatura real del dispositivo */}
            {featuredReading?.temperature !== null && featuredReading?.temperature !== undefined && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, color: 'var(--cc-ink-inv-3)' }}>Temperatura · últimas 24 h (estimado)</span>
                  <span style={{ fontSize: 12, color: 'var(--cc-ink-inv-2)', fontVariantNumeric: 'tabular-nums' }}>
                    {featuredReading.temperature} °C actual
                  </span>
                </div>
                <TempSparkline base={featuredReading.temperature} />
              </>
            )}

            {/* Reading tiles */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8, marginTop: 14 }}>
               {/* Temperature */}
               {featuredSensors.includes('temperature') && (
                 <div style={{ borderRadius: 10, padding: '12px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.09)' }}>
                   <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                     <Thermometer size={15} color="#7EDBE4" />
                     <span className={`cc-dot${featuredReading?.temperature !== null && featuredReading?.temperature !== undefined && featuredReading.temperature > 4 ? ' cc-dot-warn' : ''}`} style={{ width: 7, height: 7 }} />
                   </div>
                   <div style={{ fontSize: 18, fontWeight: 700, color: '#fff', fontVariantNumeric: 'tabular-nums' }}>
                     {featuredReading?.temperature !== null && featuredReading?.temperature !== undefined ? `${featuredReading.temperature} °C` : '—'}
                   </div>
                   <div style={{ fontSize: 12, color: 'var(--cc-ink-inv-3)', marginTop: 2 }}>Temperatura</div>
                 </div>
               )}
               {/* Humidity */}
               {featuredSensors.includes('humidity') && (
                 <div style={{ borderRadius: 10, padding: '12px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.09)' }}>
                   <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                     <Droplets size={15} color="#7EDBE4" />
                     <span className={`cc-dot${featuredReading?.humidity !== null && featuredReading?.humidity !== undefined && featuredReading.humidity > 90 ? ' cc-dot-warn' : ''}`} style={{ width: 7, height: 7 }} />
                   </div>
                   <div style={{ fontSize: 18, fontWeight: 700, color: '#fff', fontVariantNumeric: 'tabular-nums' }}>
                     {featuredReading?.humidity !== null && featuredReading?.humidity !== undefined ? `${featuredReading.humidity} %` : '—'}
                   </div>
                   <div style={{ fontSize: 12, color: 'var(--cc-ink-inv-3)', marginTop: 2 }}>Humedad</div>
                 </div>
               )}
               {/* Energy */}
               {featuredSensors.includes('energy') && (
                 <div style={{ borderRadius: 10, padding: '12px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.09)' }}>
                   <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                     <Zap size={15} color="#7EDBE4" />
                     <span className={`cc-dot${featuredReading?.energy === 'off' ? ' cc-dot-warn' : ''}`} style={{ width: 7, height: 7 }} />
                   </div>
                   <div style={{ fontSize: 18, fontWeight: 700, color: featuredReading?.energy === 'on' ? '#8BE3B5' : '#F9A8A8', fontVariantNumeric: 'tabular-nums' }}>
                     {featuredReading?.energy === 'on' ? 'ON' : 'OFF'}
                   </div>
                   <div style={{ fontSize: 12, color: 'var(--cc-ink-inv-3)', marginTop: 2 }}>Energía</div>
                 </div>
               )}
               {/* Fill empty columns if fewer than 3 sensors */}
               {featuredSensors.length < 3 && Array.from({ length: 3 - featuredSensors.length }).map((_, i) => (
                 <div key={i} style={{ borderRadius: 10, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }} />
               ))}
            </div>
          </>
        ) : devices.length === 0 ? (
          /* Empty state — no devices at all */
          <div style={{ textAlign: 'center', padding: '28px 0' }}>
            <Snowflake size={32} color="rgba(255,255,255,0.25)" style={{ marginBottom: 12 }} />
            <div style={{ fontSize: 14, color: 'rgba(255,255,255,0.45)', lineHeight: 1.5 }}>
              Sin dispositivos registrados
            </div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', marginTop: 6 }}>
              Los datos aparecerán aquí una vez configurado el sistema.
            </div>
          </div>
        ) : (
          /* Devices exist but none active */
          <div style={{ textAlign: 'center', padding: '28px 0' }}>
            <Snowflake size={32} color="rgba(255,255,255,0.25)" style={{ marginBottom: 12 }} />
            <div style={{ fontSize: 14, color: 'rgba(255,255,255,0.45)', lineHeight: 1.5 }}>
              {devices.length} dispositivo{devices.length !== 1 ? 's' : ''} registrado{devices.length !== 1 ? 's' : ''}
            </div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', marginTop: 6 }}>
              Ninguno activo en este momento.
            </div>
          </div>
        )}
      </div>

      {/* KPIs from real data */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 16, marginTop: 28 }}>
        {kpis.map(k => (
          <div key={k.lbl} style={{ borderLeft: '2px solid rgba(95,211,223,0.5)', paddingLeft: 12 }}>
            <div className="cc-kpi-num">{k.num}</div>
            <div className="cc-kpi-lbl">{k.lbl}</div>
          </div>
        ))}
      </div>
    </>
  );
}

// ─── Main view ─────────────────────────────────────────────────────────────────
export function LoginView() {
  const { isAuthenticated, isLoading, login } = useAuth();
  const { devices } = useDevices();
  const navigate = useNavigate();
  const location = useLocation();
  const from: string = (location.state as any)?.from?.pathname || '/app/dashboard';

  const [email,        setEmail]        = useState('');
  const [password,     setPassword]     = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [remember,     setRemember]     = useState(true);
  const [capsLock,     setCapsLock]     = useState(false);
  const [error,        setError]        = useState('');
  const [submitting,   setSubmitting]   = useState(false);
  const [selectedRole, setSelectedRole] = useState('');
  const [demoOpen,     setDemoOpen]     = useState(true);
  const [notice,       setNotice]       = useState('');
  const noticeTimer = useRef<number>();

  if (isLoading) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  gap: 12, color: 'var(--cc-ink-2)', background: '#F5F8FA' }}>
      <LoaderCircle size={20} className="cc-spin" />
      <span style={{ fontSize: 14 }}>Cargando sesión...</span>
    </div>
  );
  if (isAuthenticated) return <Navigate to="/app/dashboard" replace />;

  const fillDemo = (role: string) => {
    setSelectedRole(role);
    setEmail(`${role}@example.com`);
    setPassword('demo1234');
    setError('');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    const result = await login(email.trim(), password);
    setSubmitting(false);
    if (result.success) navigate(from, { replace: true });
    else setError(result.error ?? 'Credenciales incorrectas. Verifica tus datos.');
  };

  const soon = (what: string) => {
    setNotice(`${what} estará disponible próximamente.`);
    window.clearTimeout(noticeTimer.current);
    noticeTimer.current = window.setTimeout(() => setNotice(''), 3000);
  };

  return (
    <div className="cc-login">
      {notice && (
        <div role="status" style={{
          position: 'fixed', top: 20, left: '50%', transform: 'translateX(-50%)', zIndex: 1000,
          background: '#0D2840', color: '#fff', fontSize: 14, padding: '10px 16px', borderRadius: 10,
          boxShadow: '0 8px 24px rgba(13,40,64,.25)',
        }}>{notice}</div>
      )}

      {/* ── Panel de marca ─────────────────────────────────────────── */}
      <section className="cc-login-hero">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <Brand />
        </div>

        <div className="cc-login-hero-body cc-rise">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 22 }}>
            <div style={{ height: 2, width: 28, background: '#5FD3DF', borderRadius: 1 }} />
            <span className="cc-eyebrow" style={{ color: 'var(--cc-ink-inv-3)' }}>Cadena de frío conectada</span>
          </div>

          <h1 style={{ fontSize: 44, fontWeight: 700, lineHeight: 1.1, color: '#fff',
                       letterSpacing: '-0.025em', margin: '0 0 18px' }}>
            Cada sensor<br /><span style={{ color: '#7EDBE4', fontWeight: 500 }}>cuenta.</span>
          </h1>
          <p style={{ fontSize: 16, lineHeight: 1.65, color: 'var(--cc-ink-inv-2)', maxWidth: 440, margin: '0 0 32px' }}>
            Visibilidad del entorno, priorización de tráfico y trazabilidad de datos.
            Infraestructura IoT para lo que debe mantenerse frío.
          </p>

          {/* Tarjeta en vivo — datos reales del contexto */}
          <DeviceLiveCard devices={devices} />
        </div>

        <div className="cc-login-hero-foot" style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12,
          paddingTop: 18, borderTop: '1px solid rgba(255,255,255,0.12)',
          fontSize: 12, color: 'var(--cc-ink-inv-3)',
        }}>
          <span>ColdChain-IoT · Prototipo de monitoreo</span>
          <span style={{ fontFamily: 'monospace' }}>v2.1.0</span>
        </div>
      </section>

      {/* ── Panel de acceso ────────────────────────────────────────── */}
      <section className="cc-login-main">
        <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span className="cc-status-pill"><span className="cc-dot" />Todos los sistemas operativos</span>
          <button type="button" className="cc-btn-ghost" onClick={() => soon('El cambio de idioma')}
            style={{ width: 'auto', height: 32, padding: '0 12px', fontSize: 13, gap: 6 }}>
            <Globe size={14} /> ES
          </button>
        </div>

        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '32px 0' }}>
          <div className="cc-login-card cc-rise cc-rise-2">
            <h2 style={{ fontSize: 28, fontWeight: 700, color: 'var(--cc-ink-1)',
                         letterSpacing: '-0.02em', margin: '0 0 8px', lineHeight: 1.2 }}>
              Bienvenido de nuevo
            </h2>
            <p style={{ fontSize: 15, color: 'var(--cc-ink-2)', lineHeight: 1.6, margin: '0 0 28px' }}>
              Inicia sesión para acceder a tu entorno de monitoreo.
            </p>

            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              <div>
                <label htmlFor="login-email" className="cc-label">Correo electrónico</label>
                <div className="cc-field">
                  <Mail size={17} className="cc-field-icon" />
                  <input id="login-email" type="email" className="cc-input"
                    value={email} onChange={e => setEmail(e.target.value)}
                    required autoComplete="email" disabled={submitting}
                    placeholder="usuario@empresa.com" />
                </div>
              </div>

              <div>
                <label htmlFor="login-password" className="cc-label">Contraseña</label>
                <div className="cc-field">
                  <Lock size={17} className="cc-field-icon" />
                  <input id="login-password" type={showPassword ? 'text' : 'password'} className="cc-input cc-input-pw"
                    value={password} onChange={e => setPassword(e.target.value)}
                    onKeyUp={e => setCapsLock(e.getModifierState('CapsLock'))}
                    onBlur={() => setCapsLock(false)}
                    required autoComplete="current-password" disabled={submitting}
                    placeholder="Tu contraseña" />
                  <button type="button" className="cc-pw-toggle"
                    aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                    onClick={() => setShowPassword(v => !v)}>
                    {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </div>
                {capsLock && (
                  <div style={{ fontSize: 12, color: '#8A5A0B', marginTop: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <AlertCircle size={13} /> Bloq Mayús está activado
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--cc-ink-2)', cursor: 'pointer', margin: 0 }}>
                  <input type="checkbox" className="form-check-input" style={{ margin: 0 }}
                    checked={remember} onChange={e => setRemember(e.target.checked)} />
                  Mantener sesión iniciada
                </label>
                <button type="button" className="cc-link" onClick={() => soon('La recuperación de contraseña')}>
                  ¿Olvidaste tu contraseña?
                </button>
              </div>

              {error && (
                <div role="alert" style={{
                  display: 'flex', alignItems: 'flex-start', gap: 10, padding: '12px 14px', borderRadius: 10,
                  background: '#FEF0F0', border: '1px solid #F5C5C5', fontSize: 13, color: '#9B2828', lineHeight: 1.5,
                }}>
                  <AlertCircle size={16} style={{ marginTop: 1, flexShrink: 0 }} />
                  {error}
                </div>
              )}

              <button type="submit" disabled={submitting} className="cc-btn-primary">
                {submitting
                  ? <><LoaderCircle size={17} className="cc-spin" />Verificando...</>
                  : <>Iniciar sesión <ArrowRight size={17} /></>}
              </button>
            </form>

            {/* Demo accounts */}
            <div style={{ marginTop: 24, paddingTop: 20, borderTop: '1px solid #D9E2E8' }}>
              <button type="button" onClick={() => setDemoOpen(v => !v)} aria-expanded={demoOpen}
                style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                         background: 'none', border: 'none', padding: 0, cursor: 'pointer', borderRadius: 6 }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, fontWeight: 600, color: 'var(--cc-ink-1)' }}>
                  Usar cuenta de demostración
                  <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.07em', color: '#123B5D',
                                 background: '#D6E8F3', padding: '2px 7px', borderRadius: 4 }}>DEMO</span>
                </span>
                <ChevronDown size={18} color="var(--cc-ink-2)"
                  style={{ transition: 'transform .2s', transform: demoOpen ? 'rotate(180deg)' : 'none' }} />
              </button>

              {demoOpen && (
                <div style={{ marginTop: 14 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                    {DEMO_ROLES.map(role => (
                      <button key={role.id} type="button" disabled={submitting} onClick={() => fillDemo(role.id)}
                        aria-pressed={selectedRole === role.id}
                        className={`cc-role${selectedRole === role.id ? ' is-selected' : ''}`}>
                        <div className="cc-role-t">{role.label}</div>
                        <div className="cc-role-d">{role.desc}</div>
                      </button>
                    ))}
                  </div>
                  <div style={{ marginTop: 10, fontSize: 12, color: 'var(--cc-ink-2)' }}>
                    Contraseña para todos los roles:{' '}
                    <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#123B5D' }}>demo1234</span>
                    <span style={{ display: 'block', marginTop: 4 }}>
                      Las cuentas deben existir en la API (autenticación real contra el backend).
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        <footer className="cc-foot" style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <span>© 2026 ColdChain-IoT</span>
          <span style={{ display: 'flex', gap: 16 }}>
            <a href="#" onClick={e => { e.preventDefault(); soon('Privacidad'); }}>Privacidad</a>
            <a href="#" onClick={e => { e.preventDefault(); soon('Términos'); }}>Términos</a>
            <a href="#" onClick={e => { e.preventDefault(); soon('Soporte'); }}>Soporte</a>
          </span>
        </footer>
      </section>
    </div>
  );
}
