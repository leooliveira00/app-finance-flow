import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import MobileWarning from './components/MobileWarning.tsx';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* Fora do App: cobre também a tela de login e o carregamento inicial,
        sem depender do estado de autenticação. */}
    <MobileWarning />
    <App />
  </StrictMode>,
);
