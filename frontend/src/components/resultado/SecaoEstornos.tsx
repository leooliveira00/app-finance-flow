import type { EstornoResultado } from '../../api';
import { moeda } from '../../formatacao';
import Secao from './Secao';

/** Estornos / créditos: negativos que só subtraem no total (sem centro de custo). */
export default function SecaoEstornos({ estornos }: { estornos: EstornoResultado[] }) {
  if (estornos.length === 0) return null;
  return (
    <Secao titulo="Estornos / Créditos (não rateados por CC)" contador={estornos.length}>
      <div className="px-5 py-2 bg-slate-50 text-[11px] text-slate-500">
        Valores negativos (ex.: exclusões retroativas). Não têm centro de custo; apenas subtraem do
        total final.
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="bg-slate-50 text-slate-400 font-bold border-y border-slate-100 text-[10px] uppercase tracking-wider">
              <th className="py-3 px-5">Operadora</th>
              <th className="py-3 px-4">Titular / Referência</th>
              <th className="py-3 px-4 text-right">Vidas</th>
              <th className="py-3 px-5 text-right">Valor</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-700">
            {estornos.map((e, i) => (
              <tr key={i} className="font-medium">
                <td className="py-3 px-5 capitalize">{e.operadora}</td>
                <td className="py-3 px-4">{e.referencia}</td>
                <td className="py-3 px-4 text-right">{e.num_vidas}</td>
                <td className="py-3 px-5 text-right font-mono font-bold text-rose-600">
                  {moeda(e.valor)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Secao>
  );
}
