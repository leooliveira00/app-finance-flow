import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig} from 'vite';

import pkg from './package.json';

export default defineConfig(() => {
  return {
    plugins: [react(), tailwindcss()],
    // Versão da aplicação congelada em BUILD-TIME. A origem é o package.json
    // deste serviço, mantido em dia pelo semantic-release (ver .releaserc.json
    // na raiz). Consequência: mudar de versão só aparece na tela depois de
    // reconstruir a imagem do frontend, não com um restart do container.
    define: {
      __APP_VERSION__: JSON.stringify(pkg.version),
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      // Em dev, encaminha /api para o backend (em prod o nginx faz esse proxy).
      // Ajuste o alvo via VITE_API_PROXY (ex.: http://backend:8000 no compose).
      proxy: {
        '/api': {
          target: process.env.VITE_API_PROXY || 'http://localhost:8000',
          changeOrigin: true,
          secure: false,
        },
      },
    },
  };
});
