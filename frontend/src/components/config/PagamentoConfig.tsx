import { Building2, Info } from 'lucide-react';

export default function PagamentoConfig() {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold text-slate-900">Pagamento Unimed e Bradesco</h2>
        <p className="text-xs text-slate-500">Parâmetros do rateio de pagamento de convênios de saúde.</p>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 flex items-start gap-3">
        <div className="h-11 w-11 bg-slate-100 border border-slate-200 rounded-xl flex items-center justify-center shrink-0">
          <Building2 className="h-5 w-5 text-slate-500" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-slate-900">De-para de empresas</h3>
          <p className="text-xs text-slate-500 mt-0.5 leading-relaxed max-w-prose">
            O mapeamento das empresas das operadoras para os centros de custo do Protheus
            ainda vive no código (validators). A migração para cadastro editável nesta tela
            está planejada.
          </p>
        </div>
      </div>

      <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-3.5 flex items-start gap-2 text-xs text-indigo-700">
        <Info className="h-4 w-4 text-indigo-500 shrink-0 mt-0.5" />
        <span>Este rateio não possui parâmetros configuráveis no momento.</span>
      </div>
    </div>
  );
}
