import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// ColdChain-IoT frontend: React + Vite + Tailwind v4.
// Sin resolvers de assets de Figma: los iconos son lucide-react y los
// graficos SVG se generan por codigo (sin carpeta de assets binarios).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    dedupe: ['react', 'react-dom'],
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  assetsInclude: ['**/*.svg', '**/*.csv'],
});
