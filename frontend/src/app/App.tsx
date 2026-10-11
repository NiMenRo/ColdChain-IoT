import { BrowserRouter } from 'react-router';
import { AuthProvider } from './contexts/AuthContext';
import { DeviceProvider } from './contexts/DeviceContext';
import { ExperimentProvider } from './contexts/ExperimentContext';
import { AppRoutes } from './routes/AppRoutes';

// Bootstrap 5 se importa desde el paquete npm (ver src/main.tsx).
// La sesion mock se restaura en AuthContext desde localStorage
// ('coldchain_session') para que persista entre recargas.
export default function App() {
  return (
    <AuthProvider>
      <DeviceProvider>
        <ExperimentProvider>
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </ExperimentProvider>
      </DeviceProvider>
    </AuthProvider>
  );
}
