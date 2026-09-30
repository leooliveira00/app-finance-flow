import { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { Building2, Search } from 'lucide-react';
import type { CentroCusto, ItemResultado } from '../../api';
import { moeda } from '../../formatacao';
import { filtrarCentros } from './centrosCusto';

/**
 * Modal: reatribuir um colaborador a outro centro de custo (ajuste manual antes
 * da confirmação). Escolher um centro já fecha o modal; a busca é do modal.
 */
export default function ModalReatribuirCc({
  item,
  centros,
  nomeCc,
  onEscolher,
  onCancelar,
}: {
  item: ItemResultado;
  centros: CentroCusto[];
  nomeCc: (codigo: string) => string;
  onEscolher: (centroCusto: string) => void;
  onCancelar: () => void;
}) {
  const [busca, setBusca] = useState('');
  const lista = useMemo(() => filtrarCentros(centros, busca), [centros, busca]);

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
            <Building2 className="h-5 w-5 text-brand-900" />
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-slate-900">Reatribuir centro de custo</h3>
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">
              <strong className="text-slate-700">{item.nome}</strong> · {item.empresa} ·{' '}
              {moeda(item.valor)}. Atual: <strong>{nomeCc(item.centro_custo)}</strong> (
              {item.centro_custo}). O valor migra para o CC escolhido; o total da empresa não muda.
            </p>
          </div>
        </div>
        <div className="mt-4">
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
            {lista.map((c) => (
              <button
                key={c.id}
                onClick={() => onEscolher(c.codigo)}
                className={`w-full flex items-center justify-between gap-2 px-3 py-2 text-left cursor-pointer hover:bg-slate-50 ${c.codigo === item.centro_custo ? 'bg-slate-50' : ''}`}
              >
                <span className="min-w-0">
                  <span className="block text-sm text-slate-800 truncate">{c.nome || '—'}</span>
                  <span className="block text-[10px] font-mono text-slate-400">{c.codigo}</span>
                </span>
              </button>
            ))}
            {centros.length === 0 && (
              <p className="text-[11px] text-amber-600 p-3">Nenhum centro de custo cadastrado.</p>
            )}
            {centros.length > 0 && lista.length === 0 && (
              <p className="text-xs text-slate-400 p-3 text-center">Nenhum encontrado.</p>
            )}
          </div>
        </div>
        <div className="mt-4 flex justify-end">
          <button
            onClick={onCancelar}
            className="py-2 px-4 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 cursor-pointer"
          >
            Cancelar
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
