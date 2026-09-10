/**
 * Tipos compartilhados da SPA.
 *
 * Os tipos de dados de negócio (itens, agregados, execuções) vivem em `api.ts`,
 * junto das chamadas que os produzem. Aqui ficam só os de navegação e de UI.
 */

export interface Toast {
  id: string;
  message: string;
  type: 'success' | 'info' | 'warning' | 'error';
}

/** Abas da barra lateral. */
export type ActiveTab = 'dashboard' | 'historico' | 'configuracoes';

/** Sub-telas do fluxo de rateio dentro do painel. */
export type ViewState = 'list' | 'execution-flow' | 'result-view';
