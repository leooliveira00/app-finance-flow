import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { defineConfig, loadEnv } from 'vite';

import pkg from './package.json';

export default defineConfig(({ mode }) => {
  // O config do Vite não recebe o `.env` em process.env: loadEnv lê o arquivo
  // (e deixa uma variável do shell prevalecer sobre ele).
  const env = loadEnv(mode, process.cwd(), '');
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
      // Ajuste o alvo via VITE_API_PROXY (ver .env.example).
      proxy: {
        '/api': {
          target: env.VITE_API_PROXY || 'http://localhost:8000',
          changeOrigin: true,
          secure: false,
        },
      },
    },
  };
});
