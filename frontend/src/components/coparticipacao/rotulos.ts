/** Rótulos da coparticipação compartilhados entre a tela e seus modais. */

const ROTULO_OPERADORA: Record<string, string> = { unimed: 'Unimed', bradesco: 'Bradesco' };
export function rotuloOperadora(op: string): string {
  const chave = (op || '').toLowerCase();
  return ROTULO_OPERADORA[chave] ?? (op || '—');
}
