import { createPortal } from 'react-dom';
import { Briefcase } from 'lucide-react';

/** Confirmação de "classificar como PJ": processar já ou selecionar mais colaboradores. */
export default function ModalConfirmarPj({
  cpf,
  nome,
  onProcessarAgora,
  onSelecionarMais,
  onCancelar,
}: {
  cpf: string;
  nome: string;
  onProcessarAgora: () => void;
  onSelecionarMais: () => void;
  onCancelar: () => void;
}) {
  return createPortal(
    <div
      className="fixed inset-0 z-30 bg-slate-900/40 flex items-center justify-center p-4"
      onClick={onCancelar}
    >
      <div
        className="bg-white rounded-2xl shadow-xl max-w-sm w-full p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 rounded-xl bg-brand-50 border border-brand-100 flex items-center justify-center shrink-0">
            <Briefcase className="h-5 w-5 text-brand-900" />
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-slate-900">Classificar como PJ</h3>
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">
              <strong className="text-slate-700">{nome || cpf}</strong> será classificado como PJ.
              Deseja selecionar outros colaboradores antes de processar?
            </p>
          </div>
        </div>
        <div className="mt-5 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
          <button
            onClick={onProcessarAgora}
            className="py-2 px-4 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer"
          >
            Não, processar agora
          </button>
          <button
            onClick={onSelecionarMais}
            className="py-2 px-4 bg-brand-900 hover:bg-brand-950 text-white rounded-xl text-xs font-bold transition-colors cursor-pointer"
          >
            Sim, selecionar mais
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
