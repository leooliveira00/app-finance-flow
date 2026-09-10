import { useCallback, useEffect, useState } from 'react';
import { Toast } from '../types';
import { CheckCircle, AlertTriangle, XCircle, Info, X } from 'lucide-react';

/** Tempo na tela antes de começar a sair (erros não somem sozinhos). */
const DURACAO_MS = 5000;
/** Deve acompanhar a duração de `.animate-toast-out` no index.css. */
const SAIDA_MS = 280;

interface ToastNotificationProps {
  toasts: Toast[];
  removeToast: (id: string) => void;
}

export default function ToastNotification({ toasts, removeToast }: ToastNotificationProps) {
  return (
    <div className="fixed bottom-5 right-5 z-[60] flex flex-col gap-3 max-w-sm w-full pointer-events-none">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onClose={() => removeToast(toast.id)} />
      ))}
    </div>
  );
}

interface ToastItemProps {
  key?: string;
  toast: Toast;
  onClose: () => void;
}

function ToastItem({ toast, onClose }: ToastItemProps) {
  const [saindo, setSaindo] = useState(false);

  // Dispara a animação de saída e só então remove — assim o card não some de
  // um quadro para o outro.
  const fechar = useCallback(() => {
    setSaindo(true);
    setTimeout(onClose, SAIDA_MS);
  }, [onClose]);

  useEffect(() => {
    // Erros ficam FIXOS na tela até o usuário fechar; os demais somem sozinhos.
    if (toast.type === 'error') return;
    const timer = setTimeout(fechar, DURACAO_MS);
    return () => clearTimeout(timer);
  }, [fechar, toast.type]);

  const icons = {
    success: <CheckCircle className="h-5 w-5 text-emerald-500 shrink-0" />,
    warning: <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0" />,
    error: <XCircle className="h-5 w-5 text-rose-500 shrink-0" />,
    info: <Info className="h-5 w-5 text-brand-500 shrink-0" />
  };

  // Fundo branco com uma barra lateral colorida, em vez do card inteiro tingido.
  // O tipo continua legível (ícone + barra) sem competir com o conteúdo da tela.
  const acentos = {
    success: 'border-l-emerald-400',
    warning: 'border-l-amber-400',
    error: 'border-l-rose-400',
    info: 'border-l-brand-400'
  };

  return (
    <div
      id={`toast-${toast.id}`}
      role="status"
      className={`flex items-start gap-3 p-4 rounded-xl bg-white/95 backdrop-blur-sm border border-slate-200/80
        border-l-4 shadow-md shadow-slate-900/5 text-slate-700 pointer-events-auto
        ${acentos[toast.type]} ${saindo ? 'animate-toast-out' : 'animate-toast-in'}`}
    >
      {icons[toast.type]}
      <div className="flex-1 text-sm leading-5 break-words">{toast.message}</div>
      <button
        onClick={fechar}
        className="p-0.5 rounded-md hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors shrink-0"
        aria-label="Fechar"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
