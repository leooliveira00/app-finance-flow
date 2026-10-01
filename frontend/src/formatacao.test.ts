import { describe, expect, it } from 'vitest';
import { moeda } from './formatacao';

// O Intl separa "R$" do número com espaço não separável (U+00A0); normalizar
// deixa a expectativa legível sem depender desse detalhe.
const fmt = (valor: string | number) => moeda(valor).replace(/\s/g, ' ');

describe('moeda', () => {
  it('formata número em reais, com milhar e duas casas', () => {
    expect(fmt(1234.5)).toBe('R$ 1.234,50');
  });

  it('aceita a string que o backend manda (Decimal serializado)', () => {
    expect(fmt('150.35')).toBe('R$ 150,35');
    expect(fmt('1000000')).toBe('R$ 1.000.000,00');
  });

  it('preserva o sinal de estornos e créditos', () => {
    expect(fmt('-120.00')).toBe('-R$ 120,00');
  });

  it('trata vazio e zero como R$ 0,00', () => {
    expect(fmt('')).toBe('R$ 0,00');
    expect(fmt(0)).toBe('R$ 0,00');
  });

  it('arredonda para centavos', () => {
    expect(fmt(10.006)).toBe('R$ 10,01');
    expect(fmt('0.004')).toBe('R$ 0,00');
  });
});
