import { Wifi, WifiOff, Bell, LogOut, ChevronRight } from 'lucide-react';
import { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router';
import { useAuth } from '../hooks/useAuth';
import { ROLE_LABELS } from '../config/rbac';

const sections: Record<string, string> = {
  dashboard: 'Dashboard', sensors: 'Dispositivos y sensores', traffic: 'Tráfico',
  alerts: 'Alertas', qos: 'QoS / Analytics', simulation: 'Simulación',
  settings: 'Configuración', users: 'Usuarios', audit: 'Auditoría',
};

export function TopNav() {
  const [isConnected, setIsConnected] = useState(true);
  const [menuOpen, setMenuOpen] = useState(false);
  const [bellHover, setBellHover] = useState(false);
  const [bellActive, setBellActive] = useState(false);
  const [profileHover, setProfileHover] = useState(false);
  const [profileActive, setProfileActive] = useState(false);
  const [logoutHover, setLogoutHover] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const interval = setInterval(() => setIsConnected(prev => Math.random() > 0.1 ? true : prev), 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const section = sections[location.pathname.split('/').pop() || 'dashboard'];
  const initials = user ? user.name.split(' ').map((p: string) => p[0]).join('').slice(0, 2) : '';

  return (
    <header className="cc-topnav d-flex align-items-center justify-content-between gap-3 px-3 px-md-4 px-xl-5" style={{ paddingLeft: '4rem' }}>
      <div className="d-flex align-items-center gap-2 text-muted small">
        <span className="d-none d-sm-inline">Entorno operativo</span>
        <ChevronRight size={14} className="d-none d-sm-block" />
        <span className="fw-medium" style={{ color: '#17232D' }}>{section}</span>
      </div>

      <div className="d-flex align-items-center gap-3">
        <div className="d-none d-sm-flex align-items-center gap-2 small" style={{ color: isConnected ? '#16835B' : '#C83B3B' }}>
          {isConnected ? <Wifi size={16} /> : <WifiOff size={16} />}
          <span>{isConnected ? 'MQTT conectado' : 'Desconectado'}</span>
        </div>

        {/* Bell button */}
        <button
          aria-label="Ver alertas"
          onClick={() => navigate('/app/alerts')}
          onMouseEnter={() => setBellHover(true)}
          onMouseLeave={() => { setBellHover(false); setBellActive(false); }}
          onMouseDown={() => setBellActive(true)}
          onMouseUp={() => setBellActive(false)}
          className="d-flex align-items-center justify-content-center rounded-2 border-0"
          style={{
            width: 40, height: 40,
            cursor: 'pointer',
            color: bellHover ? '#123B5D' : '#52616B',
            background: bellActive ? '#D9E2E8' : bellHover ? '#EFF4F7' : 'transparent',
            transition: 'background 0.15s, color 0.15s',
            transform: bellActive ? 'scale(0.93)' : 'scale(1)',
          }}
        >
          <Bell size={20} />
        </button>

        <div style={{ width: 1, height: 28, background: '#D9E2E8' }} />

        {/* Profile button */}
        {user && (
          <div ref={menuRef} style={{ position: 'relative' }}>
            <button
              onClick={() => setMenuOpen(o => !o)}
              onMouseEnter={() => setProfileHover(true)}
              onMouseLeave={() => { setProfileHover(false); setProfileActive(false); }}
              onMouseDown={() => setProfileActive(true)}
              onMouseUp={() => setProfileActive(false)}
              className="d-flex align-items-center gap-2 border-0 rounded-3"
              style={{
                padding: '4px 8px',
                cursor: 'pointer',
                background: profileActive
                  ? '#D9E2E8'
                  : menuOpen || profileHover
                  ? '#EFF4F7'
                  : 'transparent',
                transition: 'background 0.15s',
                transform: profileActive ? 'scale(0.97)' : 'scale(1)',
                outline: menuOpen ? '2px solid #27B3C2' : 'none',
                outlineOffset: 2,
              }}
            >
              <span
                className="d-flex align-items-center justify-content-center rounded-circle flex-shrink-0"
                style={{
                  width: 36, height: 36,
                  background: menuOpen || profileHover ? '#123B5D' : '#EAF1F5',
                  color: menuOpen || profileHover ? '#fff' : '#123B5D',
                  fontSize: 12, fontWeight: 700,
                  transition: 'background 0.15s, color 0.15s',
                }}
              >
                {initials}
              </span>
              <span className="d-none d-sm-block text-start">
                <span className="d-block fw-semibold" style={{ fontSize: 13, color: '#17232D' }}>{user.name}</span>
                <span className="d-block" style={{ fontSize: 11, color: '#52616B' }}>{ROLE_LABELS[user.role]}</span>
              </span>
              <svg
                width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
                strokeLinecap="round" strokeLinejoin="round"
                style={{
                  color: '#52616B',
                  transform: menuOpen ? 'rotate(180deg)' : 'rotate(0deg)',
                  transition: 'transform 0.2s',
                  flexShrink: 0,
                }}
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>

            {menuOpen && (
              <div
                style={{
                  position: 'absolute', right: 0, top: 'calc(100% + 6px)', zIndex: 200,
                  background: '#fff', border: '1px solid #D9E2E8', borderRadius: 10,
                  boxShadow: '0 8px 24px rgba(18,59,93,0.13)', minWidth: 210, padding: '6px 0',
                }}
              >
                <div style={{ padding: '10px 14px 8px', borderBottom: '1px solid #EFF4F7' }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#17232D' }}>{user.name}</div>
                  <div style={{ fontSize: 11, color: '#52616B', marginTop: 2 }}>{user.email}</div>
                </div>
                <button
                  onClick={async () => { setMenuOpen(false); await logout(); navigate('/login', { replace: true }); }}
                  onMouseEnter={() => setLogoutHover(true)}
                  onMouseLeave={() => setLogoutHover(false)}
                  className="d-flex align-items-center gap-2 border-0 w-100 text-start"
                  style={{
                    padding: '9px 14px',
                    fontSize: 13,
                    color: logoutHover ? '#fff' : '#C83B3B',
                    background: logoutHover ? '#C83B3B' : 'transparent',
                    cursor: 'pointer',
                    transition: 'background 0.15s, color 0.15s',
                  }}
                >
                  <LogOut size={15} /> Cerrar sesión
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
