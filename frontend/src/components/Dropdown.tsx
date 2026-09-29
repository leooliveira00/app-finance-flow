import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Search } from 'lucide-react';

export interface OpcaoDropdown {
  value: string;
  label: string;
}

interface Props {
  value: string;
  opcoes: OpcaoDropdown[];
  onChange: (value: string) => void;
  /** Classes extras do botão (ex.: 'w-full' para preencher um form). */
  className?: string;
  /** Largura do painel de opções. */
  larguraMenu?: string;
  /**
   * Força (ou desliga) o campo de busca. Sem valor, a busca aparece sozinha a
   * partir de `LIMITE_BUSCA` opções — listas curtas não ganham um campo à toa e
   * listas longas (ex.: a ferramenta passar de 10 rateios) não viram uma coluna
   * de itens para percorrer com o olho.
   */
  buscavel?: boolean;
}

/** A partir de quantas opções a busca passa a aparecer automaticamente. */
const LIMITE_BUSCA = 8;

/** Comparação sem acento e sem caixa: "coparticipacao" acha "Coparticipação". */
function normalizar(texto: string): string {
  // \u0300-\u036f = diacríticos combinantes separados pelo NFD (escapes
  // explícitos: o caractere cru é invisível no editor e some em copy/paste).
  return texto
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

/**
 * Dropdown estilizado no padrão da ferramenta (substitui o <select> nativo, cujas
 * opções o browser não estiliza). Botão com chevron + painel branco arredondado,
 * item ativo em destaque, busca opcional e fechamento ao clicar fora.
 */
export default function Dropdown({
  value,
  opcoes,
  onChange,
  className = '',
  larguraMenu = 'w-full min-w-[180px]',
  buscavel,
}: Props) {
  const [aberto, setAberto] = useState(false);
  const [busca, setBusca] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const atual = opcoes.find((o) => o.value === value) ?? opcoes[0];
  const mostrarBusca = buscavel ?? opcoes.length > LIMITE_BUSCA;

  const filtradas = useMemo(() => {
    const q = normalizar(busca.trim());
    if (!q) return opcoes;
    return opcoes.filter((o) => normalizar(o.label).includes(q));
  }, [opcoes, busca]);

  // Cada abertura começa limpa (a busca é zerada ao abrir, em `alternar`), com o
  // cursor na busca: abrir e digitar.
  useEffect(() => {
    if (aberto && mostrarBusca) inputRef.current?.focus();
  }, [aberto, mostrarBusca]);

  const alternar = () => {
    if (!aberto) setBusca('');
    setAberto(!aberto);
  };

  const fechar = () => setAberto(false);
  const selecionar = (v: string) => {
    onChange(v);
    fechar();
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={alternar}
        className={`flex items-center justify-between gap-1.5 py-2 px-3 border border-slate-200 rounded-xl text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 cursor-pointer whitespace-nowrap ${className}`}
      >
        <span className="truncate">{atual?.label}</span>
        <ChevronDown
          className={`h-3.5 w-3.5 text-slate-400 shrink-0 transition-transform ${aberto ? 'rotate-180' : ''}`}
        />
      </button>
      {aberto && (
        <>
          <div className="fixed inset-0 z-10" onClick={fechar} />
          <div
            className={`absolute left-0 top-11 z-20 ${larguraMenu} bg-white border border-slate-200 rounded-xl shadow-lg text-left overflow-hidden`}
          >
            {mostrarBusca && (
              <div className="p-2 border-b border-slate-100">
                <div className="relative">
                  <Search className="h-3.5 w-3.5 text-slate-400 absolute inset-y-0 left-2.5 my-auto" />
                  <input
                    ref={inputRef}
                    type="text"
                    value={busca}
                    onChange={(e) => setBusca(e.target.value)}
                    onKeyDown={(e) => {
                      // Enter escolhe o primeiro resultado; Esc sai sem mudar nada.
                      if (e.key === 'Enter' && filtradas.length > 0) {
                        e.preventDefault();
                        selecionar(filtradas[0].value);
                      }
                      if (e.key === 'Escape') fechar();
                    }}
                    placeholder="Buscar…"
                    className="w-full pl-8 pr-2 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                </div>
              </div>
            )}
            <div className="py-1 max-h-64 overflow-auto">
              {filtradas.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => selecionar(o.value)}
                  className={`w-full text-left px-3 py-2 text-xs hover:bg-slate-50 cursor-pointer ${o.value === value ? 'font-bold text-brand-900 bg-brand-50/50' : 'text-slate-700'}`}
                >
                  {o.label}
                </button>
              ))}
              {filtradas.length === 0 && (
                <div className="px-3 py-3 text-xs text-slate-400">Nenhuma opção encontrada.</div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
