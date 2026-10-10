import { useState, useEffect } from 'react';
import { UserPlus, Edit2, ToggleLeft, ToggleRight, Shield, X, Save, Eye, EyeOff } from 'lucide-react';
import { Table, Button, Form, Row, Col } from '../../lib/bootstrap';
import { UserRole, ROLE_LABELS } from '../../config/rbac';
import { useUsers, type ManagedUser } from '../../hooks/useUsers';

const ROLE_COLOR = '#123B5D';

function getInitials(name: string) {
  return name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
}

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
        style={{ background: '#fff', borderRadius: 12, width: '100%', maxWidth: 480,
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

// ─── Password field ────────────────────────────────────────────────────────────
function PasswordField({ value, onChange, label }: {
  value: string; onChange: (v: string) => void; label: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div>
      <Form.Label className="small fw-semibold text-muted">{label}</Form.Label>
      <div style={{ position: 'relative' }}>
        <Form.Control size="sm" type={show ? 'text' : 'password'} value={value}
          onChange={e => onChange(e.target.value)}
          style={{ paddingRight: 38 }} />
        <button type="button" onClick={() => setShow(s => !s)}
          className="border-0 bg-transparent d-flex align-items-center"
          style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                   cursor: 'pointer', color: '#52616B', padding: 0 }}>
          {show ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
      </div>
    </div>
  );
}

// ─── User Form ─────────────────────────────────────────────────────────────────
interface UserFormData { name: string; email: string; role: UserRole; password: string; confirmPassword: string; }
const EMPTY_USER: UserFormData = { name: '', email: '', role: 'operador', password: '', confirmPassword: '' };

function UserForm({ initial, mode, onSave, onCancel }: {
  initial: UserFormData; mode: 'create' | 'edit';
  onSave: (d: UserFormData) => void; onCancel: () => void;
}) {
  const [form,   setForm]   = useState<UserFormData>(initial);
  const [errors, setErrors] = useState<Partial<Record<keyof UserFormData, string>>>({});

  function validate() {
    const e: typeof errors = {};
    if (!form.name.trim())  e.name  = 'El nombre es requerido.';
    if (!form.email.trim()) e.email = 'El correo es requerido.';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) e.email = 'Formato de correo inválido.';
    if (mode === 'create') {
      if (!form.password)            e.password        = 'La contraseña es requerida.';
      else if (form.password.length < 8) e.password    = 'Mínimo 8 caracteres.';
      if (form.password !== form.confirmPassword) e.confirmPassword = 'Las contraseñas no coinciden.';
    }
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  function submit(e: React.FormEvent) { e.preventDefault(); if (validate()) onSave(form); }
  const set = (k: keyof UserFormData) => (v: string) => setForm(p => ({ ...p, [k]: v }));

  return (
    <form onSubmit={submit} noValidate>
      <Row className="g-3">
        <Col xs={12}>
          <Form.Label className="small fw-semibold text-muted">Nombre completo</Form.Label>
          <Form.Control size="sm" value={form.name} placeholder="Ej. Ana García"
            onChange={e => set('name')(e.target.value)} isInvalid={!!errors.name} />
          {errors.name && <div className="invalid-feedback d-block" style={{ fontSize: 12 }}>{errors.name}</div>}
        </Col>
        <Col xs={12}>
          <Form.Label className="small fw-semibold text-muted">Correo electrónico</Form.Label>
          <Form.Control size="sm" type="email" value={form.email} placeholder="usuario@dominio.com"
            onChange={e => set('email')(e.target.value)} isInvalid={!!errors.email} />
          {errors.email && <div className="invalid-feedback d-block" style={{ fontSize: 12 }}>{errors.email}</div>}
        </Col>
        <Col xs={12}>
          <Form.Label className="small fw-semibold text-muted">Rol</Form.Label>
          <Form.Select size="sm" value={form.role} onChange={e => set('role')(e.target.value)}>
            {(Object.keys(ROLE_LABELS) as UserRole[]).map(r => (
              <option key={r} value={r}>{ROLE_LABELS[r]}</option>
            ))}
          </Form.Select>
          <div className="text-muted mt-1" style={{ fontSize: 11 }}>
            El rol determina los permisos de acceso en el sistema.
          </div>
        </Col>

        {mode === 'create' && (
          <>
            <Col xs={12}>
              <PasswordField label="Contraseña" value={form.password} onChange={set('password')} />
              {errors.password && <div className="mt-1" style={{ fontSize: 12, color: '#C83B3B' }}>{errors.password}</div>}
              <div className="text-muted mt-1" style={{ fontSize: 11 }}>Mínimo 8 caracteres.</div>
            </Col>
            <Col xs={12}>
              <PasswordField label="Confirmar contraseña" value={form.confirmPassword} onChange={set('confirmPassword')} />
              {errors.confirmPassword && <div className="mt-1" style={{ fontSize: 12, color: '#C83B3B' }}>{errors.confirmPassword}</div>}
            </Col>
          </>
        )}
      </Row>

      <div className="d-flex gap-2 justify-content-end mt-4">
        <Button type="button" variant="outline-secondary" size="sm" onClick={onCancel}>Cancelar</Button>
        <Button type="submit" variant="primary" size="sm" className="d-flex align-items-center gap-1">
          <Save size={13} />{mode === 'create' ? 'Crear usuario' : 'Guardar cambios'}
        </Button>
      </div>
    </form>
  );
}

// ─── Main view (fuente: GET /users + POST/PATCH, solo admin) ──────────────────
export function UserManagementView() {
  const store = useUsers();
  const { users } = store;
  const [modal, setModal] = useState<{ open: boolean; mode: 'create' | 'edit'; user: ManagedUser | null }>({
    open: false, mode: 'create', user: null,
  });
  const [modalError, setModalError] = useState<string | null>(null);
  const [rowBusyId, setRowBusyId] = useState<string | null>(null);

  const toggle = async (id: string) => {
    const target = users.find(u => u.id === id);
    if (!target || rowBusyId) return;
    setRowBusyId(id);
    const result = await store.setActive(id, !target.active);
    setRowBusyId(null);
    if (!result.ok) alert(result.error ?? 'No se pudo cambiar el estado.');
  };
  const roleCount   = (role: UserRole) => users.filter(u => u.role === role).length;
  const activeCount = users.filter(u => u.active).length;

  function openCreate() { setModalError(null); setModal({ open: true, mode: 'create', user: null }); }
  function openEdit(u: ManagedUser) { setModalError(null); setModal({ open: true, mode: 'edit', user: u }); }
  function closeModal() { setModal(m => ({ ...m, open: false })); setModalError(null); }

  async function handleSave(data: UserFormData) {
    setModalError(null);
    if (modal.mode === 'create') {
      const result = await store.createUser({ name: data.name, email: data.email, role: data.role, password: data.password });
      if (result.ok) closeModal();
      else setModalError(result.error ?? 'Error al crear el usuario.');
    } else if (modal.user) {
      const result = await store.updateUser(modal.user.id, { name: data.name, email: data.email, role: data.role });
      if (result.ok) closeModal();
      else setModalError(result.error ?? 'Error al actualizar el usuario.');
    }
  }

  const modalInitial: UserFormData = modal.user
    ? { name: modal.user.name, email: modal.user.email, role: modal.user.role, password: '', confirmPassword: '' }
    : EMPTY_USER;

  return (
    <div>
      <div className="d-flex justify-content-between align-items-start mb-4 flex-wrap gap-3">
        <div>
          <h1 className="mb-1" style={{ fontSize: 22, fontWeight: 700 }}>Gestión de Usuarios</h1>
          <p className="text-muted small mb-0">Administración de cuentas y roles del sistema</p>
        </div>
        <Button variant="primary" className="d-flex align-items-center gap-2" onClick={openCreate}>
          <UserPlus size={15} />Nuevo usuario
        </Button>
      </div>

      {/* Role summary */}
      <div className="row g-3 mb-4">
        {(['admin', 'supervisor', 'operador', 'auditor'] as UserRole[]).map(role => (
          <div key={role} className="col-6 col-lg-3">
            <div className="cc-card p-3" style={{ borderLeft: `4px solid ${ROLE_COLOR}` }}>
              <div className="small fw-semibold text-muted text-uppercase mb-1"
                style={{ letterSpacing: '0.06em', fontSize: 11 }}>{ROLE_LABELS[role]}</div>
              <div style={{ fontSize: 26, fontWeight: 700 }}>{roleCount(role)}</div>
            </div>
          </div>
        ))}
      </div>

      {/* User table (fuente: GET /users) */}
      {(store.isAuthBlocked || store.isForbidden || store.isConfigMissing) && !store.isLoading && (
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-3 rounded-3 px-4 py-3 mb-4"
          style={{ background: '#FFF5E3', border: '1px solid #ffda6a', borderLeft: '4px solid #C47A00' }}>
          <p className="mb-0 small">
            <strong>No se pudieron cargar los usuarios.</strong>{' '}
            {store.isConfigMissing
              ? 'Falta configurar VITE_API_BASE_URL en el frontend.'
              : store.isForbidden
                ? 'Acceso denegado: la gestión de usuarios requiere rol administrador.'
                : 'La API requiere autenticación Bearer. Inicie sesión nuevamente si su sesión expiró.'}
          </p>
          <button
            onClick={store.retry}
            className="border-0 bg-transparent fw-semibold"
            style={{ fontSize: 13, color: '#965D00', cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            Reintentar
          </button>
        </div>
      )}

      <div className="cc-card mb-4">
        <div className="d-flex justify-content-between align-items-center px-3 py-3 border-bottom">
          <h2 className="mb-0" style={{ fontSize: 16, fontWeight: 600 }}>Usuarios registrados</h2>
          <span className="small text-muted">{activeCount} de {users.length} activos</span>
        </div>
        <Table responsive hover className="cc-table mb-0">
          <thead>
            <tr><th>Nombre</th><th>Email</th><th>Rol</th><th>Estado</th><th>Creado</th><th>Acciones</th></tr>
          </thead>
          <tbody>
            {store.isLoading ? (
              <tr><td colSpan={6} className="text-center text-muted py-5">Cargando usuarios…</td></tr>
            ) : store.status === 'error' ? (
              <tr><td colSpan={6} className="text-center py-5" style={{ color: '#B22F2F' }}>
                No se pudieron cargar los usuarios. <button onClick={store.retry} className="border-0 bg-transparent p-0 fw-semibold" style={{ fontSize: 12, color: '#B22F2F', cursor: 'pointer' }}>Reintentar</button>
              </td></tr>
            ) : users.length === 0 ? (
              <tr><td colSpan={6} className="text-center text-muted py-5">No hay usuarios registrados.</td></tr>
            ) : users.map(user => (
              <tr key={user.id} style={{ opacity: user.active ? 1 : 0.55 }}>
                <td data-label="Nombre">
                  <div className="d-flex align-items-center gap-2">
                    <div className="d-flex align-items-center justify-content-center rounded-circle flex-shrink-0"
                      style={{ width: 34, height: 34, background: ROLE_COLOR, color: '#fff', fontSize: 12, fontWeight: 700 }}>
                      {getInitials(user.name)}
                    </div>
                    <span className="fw-medium">{user.name}</span>
                  </div>
                </td>
                <td data-label="Email" className="text-muted small">{user.email}</td>
                <td data-label="Rol">
                  <span className="d-inline-flex align-items-center gap-1 small fw-semibold rounded-pill px-2 py-1"
                    style={{ background: ROLE_COLOR + '20', color: ROLE_COLOR, border: `1px solid ${ROLE_COLOR}50` }}>
                    <Shield size={11} />{ROLE_LABELS[user.role]}
                  </span>
                </td>
                <td data-label="Estado">
                  <span className="small fw-semibold rounded-pill px-2 py-1"
                    style={{ background: user.active ? '#20c99720' : '#6c757d20',
                             color: user.active ? '#16835B' : '#52616B',
                             border: `1px solid ${user.active ? '#20c99750' : '#6c757d50'}` }}>
                    {user.active ? 'Activo' : 'Inactivo'}
                  </span>
                </td>
                <td data-label="Creado" className="small text-muted">{user.createdAt}</td>
                <td data-label="Acciones">
                  <div className="d-flex gap-2">
                    <Button variant="outline-secondary" size="sm" style={{ padding: '4px 8px' }}
                      title="Editar usuario" onClick={() => openEdit(user)}>
                      <Edit2 size={14} />
                    </Button>
                    <Button variant={user.active ? 'outline-danger' : 'outline-success'} size="sm"
                      style={{ padding: '4px 8px' }}
                      disabled={rowBusyId === user.id}
                      title={user.active ? 'Desactivar' : 'Activar'} onClick={() => toggle(user.id)}>
                      {user.active ? <ToggleRight size={14} /> : <ToggleLeft size={14} />}
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>

      {/* Modal (POST /users en creación, PATCH /users/{id} en edición) */}
      <Modal show={modal.open} onHide={closeModal}
        title={modal.mode === 'create' ? 'Nuevo usuario' : `Editar — ${modal.user?.name}`}>
        {modalError && (
          <div className="rounded-3 px-3 py-2 mb-3 small" style={{ background: '#FCEEEE', border: '1px solid #f1aeb5', color: '#B22F2F' }}>
            {modalError}
          </div>
        )}
        <UserForm key={modal.user?.id ?? 'new'} initial={modalInitial}
          mode={modal.mode} onSave={handleSave} onCancel={closeModal} />
      </Modal>
    </div>
  );
}
