import { ActiveTab, ViewState } from '../types';
import { ChevronRight, FlaskConical } from 'lucide-react';

interface HeaderProps {
  activeTab: ActiveTab;
  viewState: ViewState;
  onGoBackToDashboard: () => void;
  /** Ambiente da base de escrita do ERP ('teste' | 'producao') — vem da sessão. */
  erpAmbiente: string;
  /** Nome do rateio em execução (ex.: "Mensalidade UNIMED — Pagamento"). Vazio
   *  fora do fluxo. O rótulo era fixo em "Coparticipação de Saúde" e mentia em
   *  todos os outros rateios. */
  rateioNome?: string;
}

export default function Header({
  activeTab,
  viewState,
  onGoBackToDashboard,
  erpAmbiente,
  rateioNome,
}: HeaderProps) {
  // Determine breadcrumb items based on state
  const getBreadcrumbs = () => {
    if (activeTab === 'historico') {
      return [
        { label: 'FinanceFlow', action: null },
        { label: 'Histórico de execuções', action: null },
      ];
    }
    if (activeTab === 'configuracoes') {
      return [
        { label: 'FinanceFlow', action: null },
        { label: 'Configurações', action: null },
      ];
    }

    // activeTab is 'dashboard'
    const base = [{ label: 'Painel', action: viewState !== 'list' ? onGoBackToDashboard : null }];

    // O rateio em execução identifica a trilha; sem ele, "Nova execução" basta.
    const trilhaRateio = rateioNome
      ? [{ label: rateioNome, action: null }]
      : [{ label: 'Nova execução', action: null }];

    if (viewState === 'execution-flow') {
      return [...base, ...trilhaRateio, { label: 'Importação', action: null }];
    }
    if (viewState === 'result-view') {
      return [...base, ...trilhaRateio, { label: 'Resultado do processamento', action: null }];
    }

    return [
      { label: 'FinanceFlow', action: null },
      { label: 'Painel geral', action: null },
    ];
  };

  const breadcrumbs = getBreadcrumbs();

  return (
    <header className="h-16 bg-white border-b border-slate-200/80 px-8 flex items-center sticky top-0 z-10 select-none">
      {/* Breadcrumb Navigation */}
      <nav className="flex items-center space-x-1.5 text-xs text-slate-500 font-medium">
        {breadcrumbs.map((crumb, index) => {
          const isLast = index === breadcrumbs.length - 1;
          return (
            <div key={index} className="flex items-center space-x-1.5">
              {index > 0 && <ChevronRight className="h-3.5 w-3.5 text-slate-300" />}
              {crumb.action ? (
                <button
                  onClick={crumb.action}
                  className="hover:text-brand-700 hover:underline cursor-pointer transition-colors"
                >
                  {crumb.label}
                </button>
              ) : (
                <span className={isLast ? 'text-slate-800 font-semibold' : ''}>{crumb.label}</span>
              )}
            </div>
          );
        })}
      </nav>

      {/* Enquanto a base de escrita do ERP não for a oficial, a sessão inteira fica
          marcada: nenhum lançamento feito aqui é um título real. */}
      {erpAmbiente !== 'producao' && (
        <div
          className="ml-auto flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800"
          title="Os lançamentos estão sendo gravados na base de teste do Protheus; nenhum registro definitivo é gerado."
        >
          <FlaskConical className="h-3.5 w-3.5" />
          ERP: ambiente de teste
        </div>
      )}
    </header>
  );
}
