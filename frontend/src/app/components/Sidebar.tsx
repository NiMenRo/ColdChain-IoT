import { useState } from 'react';
import { NavLink } from 'react-router';
import { LayoutDashboard, Cpu, Network, Bell, Activity, FlaskConical, Settings, Users, ClipboardList, Snowflake, PanelLeftClose, Menu, X, Radio } from 'lucide-react';
import { SIDEBAR_ROLES } from '../config/rbac';
import { useAuth } from '../hooks/useAuth';

const items = [
  { icon: LayoutDashboard, label: 'Dashboard',             id: 'dashboard',  path: '/app/dashboard'  },
  { icon: Cpu,             label: 'Dispositivos',           id: 'sensors',    path: '/app/sensors'    },
  { icon: Network,         label: 'Tráfico',               id: 'traffic',    path: '/app/traffic'    },
  { icon: Bell,            label: 'Alertas',               id: 'alerts',     path: '/app/alerts'     },
  { icon: Activity,        label: 'QoS / Analytics',       id: 'qos',         path: '/app/qos'         },
  { icon: FlaskConical,    label: 'Simulación',            id: 'simulation',  path: '/app/simulation'  },
  { icon: Settings,        label: 'Configuración',         id: 'settings',   path: '/app/settings'   },
  { icon: Users,           label: 'Usuarios',              id: 'users',      path: '/app/users'      },
  { icon: ClipboardList,   label: 'Auditoría',             id: 'audit',      path: '/app/audit'      },
] as const;

export function Sidebar() {
  const { role } = useAuth();
  const [open, setOpen] = useState(false);
  const [compact, setCompact] = useState(false);
  const visibleItems = items.filter(item => role && SIDEBAR_ROLES[item.id]?.includes(role));

  return (
    <>
      <button
        aria-label="Abrir navegación"
        aria-expanded={open}
        onClick={() => setOpen(true)}
        className="position-fixed d-flex d-md-none align-items-center justify-content-center rounded-3 border-0"
        style={{ left: 16, top: 20, zIndex: 30, width: 40, height: 40, background: 'transparent', color: '#123B5D' }}
      >
        <Menu size={22} />
      </button>

      {open && (
        <button
          aria-label="Cerrar navegación"
          onClick={() => setOpen(false)}
          className="position-fixed d-md-none border-0"
          style={{ inset: 0, zIndex: 40, background: 'rgba(18,59,93,0.4)' }}
        />
      )}

      <aside
        id="app-navigation"
        className={`cc-sidebar d-flex flex-column ${open ? 'position-fixed' : 'd-none d-md-flex position-sticky'} flex-column`}
        style={{
          top: 0,
          left: 0,
          height: '100vh',
          width: compact ? 80 : 248,
          zIndex: open ? 50 : undefined,
          transition: 'width 0.2s',
          flexShrink: 0,
        }}
      >
        {/* Logo */}
        <div className="cc-sidebar-header d-flex align-items-center gap-3 px-4 py-4" style={{ height: 80, flexShrink: 0 }}>
          <Snowflake size={31} strokeWidth={1.6} className="flex-shrink-0" style={{ color: '#68D0D9' }} />
          {!compact && (
            <div className="d-none d-md-block">
              <div className="text-white fw-bold text-nowrap" style={{ fontSize: 19 }}>
                ColdChain<span style={{ color: '#68D0D9', fontWeight: 400 }}>-IoT</span>
              </div>
              <div style={{ fontSize: 10, letterSpacing: '0.17em', color: '#AFC7D8' }}>MONITOREO INTELIGENTE</div>
            </div>
          )}
          <button
            aria-label="Cerrar menú"
            onClick={() => setOpen(false)}
            className="ms-auto d-md-none border-0 bg-transparent"
            style={{ color: '#AFC7D8' }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Section label */}
        {!compact && (
          <div className="px-4 pb-2 pt-4" style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.16em', color: '#AFC7D8' }}>
            ENTORNO OPERATIVO
          </div>
        )}

        {/* Nav items */}
        <nav aria-label="Navegación principal" className="flex-grow-1 overflow-y-auto px-2 py-1" style={{ overflowY: 'auto' }}>
          {visibleItems.map((item, index) => (
            <div key={item.path} style={{ marginTop: item.id === 'settings' ? 24 : 2, paddingTop: item.id === 'settings' ? 16 : 0, borderTop: item.id === 'settings' ? '1px solid #315771' : undefined }}>
              <NavLink
                title={item.label}
                to={item.path}
                onClick={() => setOpen(false)}
                className={({ isActive }) => `cc-nav-link ${isActive ? 'active' : ''}`}
                style={{ justifyContent: compact ? 'center' : undefined }}
              >
                {({ isActive }) => (
                  <>
                    <item.icon size={20} strokeWidth={1.7} style={{ flexShrink: 0, color: isActive ? '#68D0D9' : undefined }} />
                    {!compact && <span>{item.label}</span>}
                  </>
                )}
              </NavLink>
            </div>
          ))}
        </nav>

        {/* Demo badge */}
        {!compact && (
          <div className="mx-3 mb-3 rounded-3 p-3" style={{ border: '1px solid #315771' }}>
            <div className="d-flex align-items-center gap-2 fw-medium text-white" style={{ fontSize: 12 }}>
              <Radio size={15} style={{ color: '#68D0D9' }} />Entorno de demostración
            </div>
            <p className="mb-0 mt-1" style={{ fontSize: 11, color: '#AFC7D8', lineHeight: 1.5 }}>Infraestructura IoT de cadena de frío</p>
          </div>
        )}

        {/* Footer */}
        <div className="cc-sidebar-footer d-flex align-items-center justify-content-between px-4" style={{ height: 56, flexShrink: 0 }}>
          {!compact && <span style={{ fontSize: 11, color: '#AFC7D8' }}>ColdChain-IoT Â· v2.1.0</span>}
          <button
            aria-label={compact ? 'Expandir navegación' : 'Compactar navegación'}
            onClick={() => setCompact(!compact)}
            className="d-none d-xl-block border-0 bg-transparent"
            style={{ color: '#AFC7D8' }}
          >
            <PanelLeftClose size={18} />
          </button>
        </div>
      </aside>
    </>
  );
}
