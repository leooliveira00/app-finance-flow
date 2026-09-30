import { CheckCircle2, XCircle } from 'lucide-react';
import type { Resultado } from '../../api';
import { moeda } from '../../formatacao';
import Secao from './Secao';

/**
 * Reconciliação por empresa: o valor final a lançar (rateado + estornos) deve
 * bater com a NF/boleto. Quando não bate, decompõe a diferença entre as
 * divergências não rateadas e o que ficou sem explicação (extração/arquivo).
 */
export default function SecaoReconciliacao({ resultado }: { resultado: Resultado }) {
  if (resultado.reconciliacao.length === 0) return null;
  return (
    <Secao titulo="Reconciliação com NF / Boleto" contador={resultado.reconciliacao.length}>
      {/* Consistência POR EMPRESA: valor final a lançar (rateado + estornos) deve = documento. */}
      <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-3">
        {resultado.reconciliacao.map((r, i) => {
          const doc = Number(r.valor_documento || 0);
          const valorFinal = Number(r.valor_base || 0);
          const diferenca = Number(r.diferenca || 0);
          const consistente = r.bate;
          const mesma = (e: string | null) =>
            (e || '').toUpperCase().trim() === (r.empresa || '').toUpperCase().trim();
          const rateadoEmp = resultado.itens
            .filter((it) => mesma(it.empresa))
            .reduce((s, it) => s + Number(it.valor || 0), 0);
          const estornoEmp = resultado.estornos
            .filter((e) => mesma(e.empresa))
            .reduce((s, e) => s + Number(e.valor || 0), 0);
          const divsEmp = resultado.divergencias.filter((d) => mesma(d.empresa));
          const somaDiv = divsEmp.reduce((s, d) => s + Number(d.valor || 0), 0);
          const naoExplicado = diferenca - somaDiv;
          return (
            <div
              key={i}
              className={`rounded-xl border p-4 ${consistente ? 'border-emerald-200 bg-emerald-50/40' : 'border-rose-200 bg-rose-50/40'}`}
            >
              <div className="flex items-center gap-2 mb-3">
                {consistente ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                ) : (
                  <XCircle className="h-4 w-4 text-rose-500" />
                )}
                <span className="text-sm font-bold text-slate-900">
                  {r.empresa || '(empresa não identificada)'}
                </span>
                <span className="text-[10px] text-slate-400 capitalize">
                  · {r.operadora} · {r.operadora === 'unimed' ? 'NF' : 'boleto'}
                </span>
                <span
                  className={`ml-auto text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded border ${consistente ? 'bg-emerald-100 text-emerald-700 border-emerald-200' : 'bg-rose-100 text-rose-700 border-rose-200'}`}
                >
                  {consistente ? 'Consistente' : 'Inconsistência'}
                </span>
              </div>
              <div className="text-xs font-mono space-y-1 max-w-md">
                <div className="flex justify-between">
                  <span className="text-slate-600">Documento (NF/boleto)</span>
                  <span className="font-semibold">{moeda(doc)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-600">Valor final a lançar</span>
                  <span className="font-semibold">{moeda(valorFinal)}</span>
                </div>
                <div className="flex justify-between text-[11px] text-slate-400">
                  <span className="pl-3">
                    rateado {moeda(rateadoEmp)} · estornos {moeda(estornoEmp)}
                  </span>
                  <span />
                </div>
                <div
                  className={`flex justify-between border-t border-slate-200 pt-1 font-bold ${consistente ? 'text-emerald-700' : 'text-rose-700'}`}
                >
                  <span>Diferença (documento − final)</span>
                  <span>{moeda(diferenca)}</span>
                </div>
                {!consistente && (
                  <div className="pt-1 pl-3 text-[11px] text-slate-500 space-y-0.5">
                    <div className="flex justify-between">
                      <span>├ Divergências não rateadas ({divsEmp.length})</span>
                      <span>{moeda(somaDiv)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>└ Não explicado (extração/arquivo)</span>
                      <span>{moeda(naoExplicado)}</span>
                    </div>
                  </div>
                )}
              </div>
              <p className="text-[11px] mt-2 leading-relaxed text-slate-500">
                {consistente
                  ? 'O valor final a lançar (com estornos já abatidos) confere com o documento desta empresa.'
                  : 'O valor a lançar difere do documento. Resolva as divergências desta empresa. "Não explicado" indica erro de extração ou arquivo do período/empresa errado.'}
              </p>
            </div>
          );
        })}
      </div>
    </Secao>
  );
}
