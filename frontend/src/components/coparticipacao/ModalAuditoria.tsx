import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import type { ItemCopartResultado } from '../../api';
import { moeda } from '../../formatacao';
import CpfCell from '../CpfCell';
import { rotuloOperadora } from './rotulos';
import TabelaOcorrencias from './TabelaOcorrencias';

function Campo({ label, valor, destaque }: { label: string; valor: string; destaque?: boolean }) {
  return (
    <div className="bg-slate-50 border border-slate-100 rounded-xl p-2.5">
      <span className="block text-[9px] font-bold text-slate-400 uppercase tracking-wide">
        {label}
      </span>
      <span
        className={`block font-mono font-bold ${destaque ? 'text-brand-950' : 'text-slate-800'}`}
      >
        {valor}
      </span>
    </div>
  );
}

/** Auditoria do cálculo de um item: faixa, teto e a classificação de cada evento. */
export default function ModalAuditoria({
  item,
  onClose,
}: {
  item: ItemCopartResultado;
  onClose: () => void;
}) {
  return createPortal(
    <div
      className="fixed inset-0 z-30 bg-slate-900/40 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl max-w-2xl w-full max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-5 border-b border-slate-100 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-slate-900 truncate">{item.nome}</h3>
            <p className="text-xs text-slate-500 font-mono flex items-center gap-1 flex-wrap">
              <CpfCell cpf={item.cpf} /> ·{' '}
              {item.pj ? 'PJ (salário padrão)' : 'CLT (salário da API)'}
              {/* A auditoria é do plano desta linha; o teto abaixo é da PESSOA. */}
              <span>· {rotuloOperadora(item.operadora)}</span>
              {item.matricula && <span>· Matrícula {item.matricula}</span>}
              {item.filial && <span>· Filial {item.filial}</span>}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="p-5 space-y-4 overflow-y-auto">
          <div>
            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-2">
              Faixa salarial atribuída
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              {/* Salário e Teto são dados de auditoria: só vêm da API para admin_area/admin. */}
              {item.salario != null && <Campo label="Salário usado" valor={moeda(item.salario)} />}
              <Campo label="Faixa" valor={item.faixa} />
              {item.teto != null && <Campo label="Teto" valor={moeda(item.teto)} />}
              <Campo label="A descontar" valor={moeda(item.valor_descontado)} destaque />
            </div>
            {item.teto_aplicado && (
              <p className="text-[11px] text-amber-700 mt-2">
                Teto atingido. O limite é do colaborador, sobre a soma dos planos; o valor bruto
                deste plano é {moeda(item.valor_bruto)}. <strong>Não enviado ao ERP</strong>: requer
                tratativa manual.
              </p>
            )}
            {item.pj && (
              <p className="text-[11px] text-brand-800 mt-2">
                Colaborador PJ: salário padrão aplicado, sem consulta ao Protheus.
              </p>
            )}
          </div>
          <div>
            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1">
              Classificação por evento ({item.ocorrencias.length})
            </div>
            <TabelaOcorrencias ocorrencias={item.ocorrencias} />
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
