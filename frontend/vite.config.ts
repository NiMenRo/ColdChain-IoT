import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// ColdChain-IoT frontend: React + Vite + Tailwind v4.
// Sin resolvers de assets de Figma: los iconos son lucide-react y los
// graficos SVG se generan por codigo (sin carpeta de assets binarios).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Host/port fijos en IPv4: evitan deriva silenciosa a :5174 y orígenes
  // [::1] que el backend no reconoce (CORS). URL canónica: http://127.0.0.1:5173
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
  },
  resolve: {
    dedupe: ['react', 'react-dom'],
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  assetsInclude: ['**/*.svg', '**/*.csv'],
});
