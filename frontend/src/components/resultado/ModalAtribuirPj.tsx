import { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { Briefcase, Check, Search } from 'lucide-react';
import type { CentroCusto, DivergenciaResultado } from '../../api';
import { filtrarCentros } from './centrosCusto';

/**
 * Modal: atribuir uma divergência (titular não encontrado / PJ sem centro de
 * custo) a PJ, escolhendo o centro de custo. A busca e a seleção são do modal:
 * ele é montado a cada abertura, então sempre começa limpo.
 */
export default function ModalAtribuirPj({
  divergencia,
  centros,
  onCancelar,
  onConfirmar,
}: {
  divergencia: DivergenciaResultado;
  centros: CentroCusto[];
  onCancelar: () => void;
  onConfirmar: (centroCusto: string) => void;
}) {
  const [busca, setBusca] = useState('');
  const [selecionado, setSelecionado] = useState('');
  const filtrados = useMemo(() => filtrarCentros(centros, busca), [centros, busca]);

  return createPortal(
    <div
      className="fixed inset-0 z-30 bg-slate-900/40 flex items-center justify-center p-4"
      onClick={onCancelar}
    >
      <div
        className="bg-white rounded-2xl shadow-xl max-w-md w-full p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 rounded-xl bg-brand-50 border border-brand-100 flex items-center justify-center shrink-0">
            <Briefcase className="h-5 w-5 text-brand-900" />
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-slate-900">Atribuir a PJ</h3>
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">
              <strong className="text-slate-700">
                {divergencia.nome || divergencia.referencia}
              </strong>{' '}
              será cadastrado como PJ e rateado ao centro de custo escolhido
              {divergencia.empresa ? (
                <>
                  {' '}
                  (empresa <strong>{divergencia.empresa}</strong>)
                </>
              ) : null}
              . Passa a valer também nas próximas execuções.
            </p>
          </div>
        </div>
        <div className="mt-4">
          <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1">
            Centro de custo
          </label>
          <div className="relative">
            <Search className="h-4 w-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              autoFocus
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar por código ou nome…"
              className="w-full pl-9 pr-3 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-200"
            />
          </div>
          <div className="mt-2 border border-slate-200 rounded-lg max-h-60 overflow-y-auto divide-y divide-slate-100">
            {filtrados.map((c) => {
              const sel = c.codigo === selecionado;
              return (
                <button
                  key={c.id}
                  onClick={() => setSelecionado(c.codigo)}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-left cursor-pointer transition-colors ${sel ? 'bg-brand-50' : 'hover:bg-slate-50'}`}
                >
                  <span
                    className={`h-4 w-4 rounded-full border flex items-center justify-center shrink-0 ${sel ? 'bg-brand-900 border-brand-900' : 'border-slate-300'}`}
                  >
                    {sel && <Check className="h-2.5 w-2.5 text-white" />}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm text-slate-800 truncate">{c.nome || '—'}</span>
                    <span className="block text-[10px] font-mono text-slate-400">{c.codigo}</span>
                  </span>
                </button>
              );
            })}
            {centros.length === 0 && (
              <p className="text-[11px] text-amber-600 p-3">
                Nenhum centro de custo cadastrado. Cadastre em Configurações ▸ Centros de custo.
              </p>
            )}
            {centros.length > 0 && filtrados.length === 0 && (
              <p className="text-xs text-slate-400 p-3 text-center">
                Nenhum centro de custo encontrado.
              </p>
            )}
          </div>
          {busca.trim() === '' && centros.length > filtrados.length && (
            <p className="text-[10px] text-slate-400 mt-1">
              Mostrando {filtrados.length} de {centros.length}. Digite para refinar.
            </p>
          )}
        </div>
        <div className="mt-5 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
          <button
            onClick={onCancelar}
            className="py-2 px-4 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 cursor-pointer"
          >
            Cancelar
          </button>
          <button
            onClick={() => onConfirmar(selecionado)}
            disabled={!selecionado}
            className="py-2 px-4 bg-brand-900 hover:bg-brand-950 text-white rounded-xl text-xs font-bold cursor-pointer disabled:opacity-50"
          >
            Atribuir e reprocessar
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
