import type { OcorrenciaCopart } from '../../api';
import { moeda } from '../../formatacao';

/** Ocorrências (eventos) de um colaborador — usada na linha expandida e na auditoria. */
export default function TabelaOcorrencias({ ocorrencias }: { ocorrencias: OcorrenciaCopart[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="text-slate-400 border-b border-slate-100 text-left">
            <th className="py-1.5 pr-3 font-bold">Data</th>
            <th className="py-1.5 pr-3 font-bold">Beneficiário</th>
            <th className="py-1.5 pr-3 font-bold">Procedimento</th>
            <th className="py-1.5 pr-3 font-bold">Classificação</th>
            <th className="py-1.5 text-right font-bold">Valor</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 text-slate-700">
          {ocorrencias.map((o, j) => (
            <tr key={j}>
              <td className="py-1.5 pr-3 text-slate-500 whitespace-nowrap">{o.data || '—'}</td>
              <td className="py-1.5 pr-3">{o.beneficiario}</td>
              <td className="py-1.5 pr-3">
                {o.procedimento}
                {!o.classificado && (
                  <span className="ml-1.5 text-[9px] font-bold text-rose-600 bg-rose-50 border border-rose-200 px-1 py-0.5 rounded">
                    não mapeado
                  </span>
                )}
              </td>
              <td className="py-1.5 pr-3 capitalize">
                {o.tipo || <span className="text-rose-500">—</span>}
              </td>
              <td className="py-1.5 text-right font-mono">{moeda(o.valor)}</td>
            </tr>
          ))}
          {ocorrencias.length === 0 && (
            <tr>
              <td colSpan={5} className="py-2 text-slate-400">
                Nenhuma ocorrência registrada.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
