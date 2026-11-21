import { FormEvent, useEffect, useState } from 'react';
import { ArrowLeft, ArrowRight, CheckCircle, KeyRound, LoaderCircle, Mail } from 'lucide-react';
import { Link, useNavigate } from 'react-router';
import { ApiError } from '../../../../services/api/client';
import {
  apiConfirmPasswordReset,
  apiRequestPasswordReset,
} from '../../../../services/api/auth';

interface PasswordResetViewProps {
  mode: 'request' | 'confirm';
}

const fieldStyle = {
  width: '100%',
  border: '1px solid #D9E2E8',
  borderRadius: 9,
  padding: '12px 14px',
  fontSize: 14,
};

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.code === 'NETWORK') {
    return 'No se pudo conectar con el servidor. Inténtalo nuevamente.';
  }
  if (error instanceof ApiError && error.status === 503) {
    return 'El servicio de correo no está disponible en este momento.';
  }
  if (error instanceof ApiError && error.status === 400) {
    return 'El enlace no es válido o ya venció. Solicita uno nuevo.';
  }
  if (error instanceof ApiError && error.status === 422) {
    return 'La contraseña debe tener al menos 8 caracteres y no superar el límite permitido.';
  }
  return 'No se pudo completar la solicitud. Inténtalo nuevamente.';
}

export function PasswordResetView({ mode }: PasswordResetViewProps) {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [complete, setComplete] = useState(false);
  const [token] = useState(() => (
    typeof window === 'undefined'
      ? ''
      : new URLSearchParams(window.location.hash.slice(1)).get('token') ?? ''
  ));

  useEffect(() => {
    if (token) {
      window.history.replaceState(
        window.history.state,
        '',
        `${window.location.pathname}${window.location.search}`,
      );
    }
  }, [token]);

  const isRequest = mode === 'request';
  const title = isRequest ? 'Recuperar contraseña' : 'Crear nueva contraseña';

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    if (!isRequest && !token) {
      setError('El enlace no es válido o ya venció. Solicita uno nuevo.');
      return;
    }
    if (!isRequest && password !== confirmPassword) {
      setError('Las contraseñas no coinciden.');
      return;
    }

    setSubmitting(true);
    try {
      if (isRequest) {
        await apiRequestPasswordReset(email.trim());
      } else {
        await apiConfirmPasswordReset(token, password);
      }
      setComplete(true);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main
      className="min-vh-100 d-flex align-items-center justify-content-center px-3 py-5"
      style={{ background: '#F5F8FA', fontFamily: "'Inter', sans-serif" }}
    >
      <section
        className="bg-white rounded-4 shadow-sm w-100 p-4 p-md-5"
        style={{ maxWidth: 460, border: '1px solid #E5EBEF' }}
      >
        <Link
          to="/login"
          className="d-inline-flex align-items-center gap-2 text-decoration-none mb-4"
          style={{ color: '#123B5D', fontWeight: 700 }}
        >
          <span aria-hidden="true">❄</span>
          ColdChain-IoT
        </Link>

        <div
          className="d-flex align-items-center justify-content-center rounded-3 mb-4"
          style={{ width: 48, height: 48, background: '#E8F5F7', color: '#167A89' }}
        >
          {isRequest ? <Mail size={23} /> : <KeyRound size={23} />}
        </div>
        <h1 className="h3 fw-bold mb-2" style={{ color: '#123B5D' }}>{title}</h1>

        {complete ? (
          <div role="status" className="mt-4">
            <p className="d-flex align-items-start gap-2 mb-4" style={{ color: '#286B4D', lineHeight: 1.6 }}>
              <CheckCircle size={19} className="flex-shrink-0 mt-1" />
              {isRequest
                ? 'Si el correo corresponde a una cuenta activa, recibirás instrucciones para restablecer la contraseña. Revisa también la carpeta de spam.'
                : 'Tu contraseña fue actualizada. Ya puedes iniciar sesión con la nueva contraseña.'}
            </p>
            <button
              type="button"
              onClick={() => navigate('/login', { replace: true })}
              className="btn w-100 d-flex align-items-center justify-content-center gap-2"
              style={{ background: '#123B5D', color: '#fff', minHeight: 46 }}
            >
              Ir al inicio de sesión <ArrowRight size={17} />
            </button>
          </div>
        ) : (
          <>
            <p className="mb-4" style={{ color: '#60717D', lineHeight: 1.6 }}>
              {isRequest
                ? 'Ingresa el correo de tu cuenta y te enviaremos un enlace seguro para elegir una contraseña nueva.'
                : 'Elige una contraseña nueva de al menos 8 caracteres.'}
            </p>

            {!isRequest && !token ? (
              <div role="alert" className="alert alert-warning">
                El enlace no es válido o ya venció. Solicita uno nuevo para continuar.
              </div>
            ) : null}

            <form onSubmit={handleSubmit} className="d-flex flex-column gap-3">
              {isRequest ? (
                <div>
                  <label htmlFor="reset-email" className="form-label fw-semibold">Correo electrónico</label>
                  <input
                    id="reset-email"
                    type="email"
                    autoComplete="email"
                    required
                    maxLength={254}
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    disabled={submitting}
                    className="form-control"
                    style={fieldStyle}
                  />
                </div>
              ) : (
                <>
                  <div>
                    <label htmlFor="reset-password" className="form-label fw-semibold">Nueva contraseña</label>
                    <input
                      id="reset-password"
                      type="password"
                      autoComplete="new-password"
                      required
                      minLength={8}
                      maxLength={72}
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      disabled={submitting || !token}
                      className="form-control"
                      style={fieldStyle}
                    />
                  </div>
                  <div>
                    <label htmlFor="reset-password-confirm" className="form-label fw-semibold">Confirmar contraseña</label>
                    <input
                      id="reset-password-confirm"
                      type="password"
                      autoComplete="new-password"
                      required
                      minLength={8}
                      maxLength={72}
                      value={confirmPassword}
                      onChange={(event) => setConfirmPassword(event.target.value)}
                      disabled={submitting || !token}
                      className="form-control"
                      style={fieldStyle}
                    />
                  </div>
                </>
              )}

              {error && <div role="alert" className="alert alert-danger mb-0">{error}</div>}

              <button
                type="submit"
                disabled={submitting || (!isRequest && !token)}
                className="btn w-100 d-flex align-items-center justify-content-center gap-2 mt-1"
                style={{ background: '#123B5D', color: '#fff', minHeight: 46 }}
              >
                {submitting
                  ? <><LoaderCircle size={17} className="cc-spin" />Procesando...</>
                  : <>{isRequest ? 'Enviar enlace' : 'Restablecer contraseña'} <ArrowRight size={17} /></>}
              </button>
            </form>
          </>
        )}

        <Link
          to="/login"
          className="d-flex align-items-center justify-content-center gap-2 mt-4 text-decoration-none"
          style={{ color: '#356078', fontSize: 14 }}
        >
          <ArrowLeft size={15} /> Volver al inicio de sesión
        </Link>
      </section>
    </main>
  );
}
