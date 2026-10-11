import { useNavigate } from 'react-router';
import { ShieldX, LayoutDashboard, ArrowLeft, Snowflake } from 'lucide-react';
import { useAuth } from '../../../hooks/useAuth';
import { ROLE_LABELS } from '../../../config/rbac';

export function ForbiddenView() {
  const navigate = useNavigate();
  const { user } = useAuth();
  return <div className="flex min-h-screen items-center justify-center bg-background p-6"><div className="max-w-lg text-center"><div className="mx-auto mb-6 flex size-16 items-center justify-center rounded-2xl bg-destructive/5 text-destructive"><ShieldX size={30} /></div><p className="mb-3 font-mono text-sm font-medium text-destructive">ERROR 403</p><h1 className="text-[30px] font-semibold">Acceso no autorizado</h1><p className="mt-4 text-sm leading-6 text-muted-foreground">No tienes permisos para acceder a esta sección. Regresa al dashboard para consultar los módulos disponibles para tu rol.</p>{user && <p className="mt-5 text-xs text-muted-foreground">Sesión activa: <span className="font-medium text-foreground">{user.name}</span> · {ROLE_LABELS[user.role]}</p>}<div className="mt-8 flex flex-wrap justify-center gap-3"><button onClick={() => navigate('/app/dashboard', { replace: true })} className="flex min-h-11 items-center gap-2 rounded-lg bg-primary px-5 text-sm text-white hover:bg-[#1F6F8B]"><LayoutDashboard size={17} />Volver al Dashboard</button><button onClick={() => navigate(-1)} className="flex min-h-11 items-center gap-2 rounded-lg border border-border bg-white px-5 text-sm text-primary hover:bg-muted"><ArrowLeft size={17} />Ir atrás</button></div><p className="mt-12 flex items-center justify-center gap-2 text-xs text-muted-foreground"><Snowflake size={15} />ColdChain-IoT · v2.1.0</p></div></div>;
}
