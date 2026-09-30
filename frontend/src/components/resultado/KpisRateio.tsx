import { AlertTriangle, Banknote, Users } from 'lucide-react';
import { moeda } from '../../formatacao';

/** Cards de resumo do rateio: colaboradores, valor final e divergências/avisos. */
export default function KpisRateio({
  totalItens,
  valorFinal,
  valorRateado,
  totalEstornos,
  qtdDivergencias,
  qtdAvisos,
}: {
  totalItens: number;
  valorFinal: number;
  valorRateado: number;
  totalEstornos: number;
  qtdDivergencias: number;
  qtdAvisos: number;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-sm flex items-center gap-4">
        <div className="h-12 w-12 bg-brand-50 border border-brand-100 rounded-xl flex items-center justify-center shrink-0">
          <Users className="h-6 w-6 text-brand-900" />
        </div>
        <div>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
            Colaboradores Rateados
          </span>
          <span className="text-2xl font-bold text-slate-900">{totalItens}</span>
        </div>
      </div>
      <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-sm flex items-center gap-4">
        <div className="h-12 w-12 bg-brand-950 rounded-xl flex items-center justify-center shrink-0 shadow-sm">
          <Banknote className="h-6 w-6 text-brand-300" />
        </div>
        <div>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
            Valor Final
          </span>
          <span className="text-2xl font-black text-brand-950 font-mono">{moeda(valorFinal)}</span>
          {totalEstornos !== 0 && (
            <span className="text-[10px] text-slate-500 block">
              rateado {moeda(valorRateado)} + estornos {moeda(totalEstornos)}
            </span>
          )}
        </div>
      </div>
      <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-sm flex items-center gap-4">
        <div className="h-12 w-12 bg-amber-50 border border-amber-100 rounded-xl flex items-center justify-center shrink-0">
          <AlertTriangle className="h-6 w-6 text-amber-500" />
        </div>
        <div>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
            Divergências / Avisos
          </span>
          <span className="text-2xl font-bold text-slate-900">
            {qtdDivergencias} <span className="text-base text-slate-400">/ {qtdAvisos}</span>
          </span>
        </div>
      </div>
    </div>
  );
}
