import { useState, type ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';

/** Card colapsável das telas de resultado. `defaultAberto` controla o estado inicial. */
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
  return (
    <div
      className={`bg-white rounded-2xl border shadow-sm overflow-hidden ${destaque ? 'border-brand-300 ring-1 ring-brand-100' : 'border-slate-200/80'}`}
    >
      <div
        className="p-4 px-5 flex items-center justify-between gap-3 cursor-pointer select-none"
        onClick={() => setAberto((a) => !a)}
      >
        <div className="flex items-center gap-2 min-w-0">
          <ChevronRight
            className={`h-4 w-4 text-slate-400 transition-transform shrink-0 ${aberto ? 'rotate-90' : ''}`}
          />
          <h3
            className={`text-sm font-bold truncate ${destaque ? 'text-brand-950' : 'text-slate-900'}`}
          >
            {titulo}
          </h3>
          {contador != null && (
            <span className="text-[11px] font-semibold bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full shrink-0">
              {contador}
            </span>
          )}
        </div>
      </div>
      {aberto && <div className="border-t border-slate-100">{children}</div>}
    </div>
  );
}
