import { useState } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, FileText, Loader2 } from 'lucide-react';

/**
 * Modal do export TXT (importação manual no ERP) de uma empresa. A coparticipação
 * não armazena competência: o usuário informa a de PAGAMENTO aqui, e o modal a
 * devolve já em AAAAMM. Montado a cada abertura, então sempre começa vazio.
 */
export default function ModalCompetenciaTxt({
  empresa,
  qtdPj,
  baixando,
  onCancelar,
  onExportar,
}: {
  empresa: string;
  qtdPj: number;
  baixando: boolean;
  onCancelar: () => void;
  onExportar: (competenciaAAAAMM: string) => void;
}) {
  // Valor do <input type="month">: AAAA-MM.
  const [competencia, setCompetencia] = useState('');
  return createPortal(
    <div
      className="fixed inset-0 z-30 bg-slate-900/40 flex items-center justify-center p-4"
      onClick={() => !baixando && onCancelar()}
    >
      <div
        className="bg-white rounded-2xl shadow-xl max-w-sm w-full p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 rounded-xl bg-brand-50 border border-brand-100 flex items-center justify-center shrink-0">
            <FileText className="h-5 w-5 text-brand-900" />
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-slate-900">Exportar TXT: {empresa}</h3>
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">
              Informe a{' '}
              <strong className="text-slate-700">
                data de referência (competência de pagamento)
              </strong>
              . Gera uma linha por colaborador de{' '}
              <strong className="text-slate-700">{empresa}</strong> no layout de importação manual
              do ERP.
            </p>
          </div>
        </div>
        <label className="block mt-4">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">
            Competência de pagamento
          </span>
          <input
            type="month"
            value={competencia}
            onChange={(e) => setCompetencia(e.target.value)}
            className="mt-1 w-full border border-slate-200 rounded-xl px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-200"
          />
        </label>
        <div className="mt-4 flex items-start gap-2 bg-amber-50 border border-amber-200/70 rounded-xl p-3 text-[11px] text-amber-900 leading-relaxed">
          <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
          <span>
            Colaboradores <strong>PJ não entram no arquivo</strong>: o desconto deles é cobrado na
            nota.
            {qtdPj > 0 && (
              <span className="block mt-1">
                {qtdPj} colaborador(es) PJ ser{qtdPj > 1 ? 'ão' : 'á'} omitido(s).
              </span>
            )}
          </span>
        </div>
        <div className="mt-5 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
          <button
            onClick={onCancelar}
            disabled={baixando}
            className="py-2 px-4 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            onClick={() => onExportar(competencia.replace(/\D/g, ''))}
            disabled={baixando || !competencia}
            className="flex items-center justify-center gap-1.5 py-2 px-4 bg-brand-900 hover:bg-brand-950 text-white rounded-xl text-xs font-bold transition-colors cursor-pointer disabled:opacity-50"
          >
            {baixando ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FileText className="h-4 w-4" />
            )}
            {baixando ? 'Gerando…' : 'Exportar TXT'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
