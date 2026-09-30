import type { CentroCusto } from '../../api';

/** Máximo de centros de custo renderizados na lista; refine a busca para ver mais. */
export const LIMITE_LISTA_CC = 60;

/** Combobox de centro de custo: filtra por código ou nome (sem diferenciar caixa). */
export function filtrarCentros(centros: CentroCusto[], busca: string): CentroCusto[] {
  const q = busca.trim().toLowerCase();
  const base = q
    ? centros.filter((c) => c.codigo.toLowerCase().includes(q) || c.nome.toLowerCase().includes(q))
    : centros;
  return base.slice(0, LIMITE_LISTA_CC);
}
