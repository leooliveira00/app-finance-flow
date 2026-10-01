import { useId, useState, type ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';

/**
 * Card colapsável das telas de resultado. `defaultAberto` controla o estado inicial.
 *
 * Padrão de accordion da WAI-ARIA: o título envolve um `<button>` (e não o
 * contrário, que é HTML inválido), com `aria-expanded` e `aria-controls`. Assim o
 * card abre por teclado (Tab + Enter/Espaço) e o leitor de tela anuncia o estado.
 */
export default function Secao({
  titulo,
  contador,
  defaultAberto = false,
  destaque = false,
  children,
}: {
  titulo: string;
  contador?: number;
  defaultAberto?: boolean;
  destaque?: boolean;
  children: ReactNode;
}) {
  const [aberto, setAberto] = useState(defaultAberto);
  const idConteudo = useId();
  return (
    <div
      className={`bg-white rounded-2xl border shadow-sm overflow-hidden ${destaque ? 'border-brand-300 ring-1 ring-brand-100' : 'border-slate-200/80'}`}
    >
      <h3>
        <button
          type="button"
          aria-expanded={aberto}
          // O conteúdo só é montado aberto; não aponte para um id inexistente.
          aria-controls={aberto ? idConteudo : undefined}
          onClick={() => setAberto((a) => !a)}
          className="w-full p-4 px-5 flex items-center gap-2 min-w-0 text-left cursor-pointer select-none focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-200"
        >
          <ChevronRight
            aria-hidden="true"
            className={`h-4 w-4 text-slate-400 transition-transform shrink-0 ${aberto ? 'rotate-90' : ''}`}
          />
          <span
            className={`text-sm font-bold truncate ${destaque ? 'text-brand-950' : 'text-slate-900'}`}
          >
            {titulo}
          </span>
          {contador != null && (
            <span className="text-[11px] font-semibold bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full shrink-0">
              {contador}
            </span>
          )}
        </button>
      </h3>
      {aberto && (
        <div id={idConteudo} className="border-t border-slate-100">
          {children}
        </div>
      )}
    </div>
  );
}
