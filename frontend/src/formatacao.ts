/** Formatação pt-BR compartilhada pelas telas. */

/** Valor em reais. Aceita a string que o backend manda (Decimal serializado). */
export function moeda(valor: string | number): string {
  return Number(valor || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}
