import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import KpisRateio from './KpisRateio';

const base = {
  totalItens: 42,
  valorFinal: 1500.5,
  valorRateado: 1500.5,
  totalEstornos: 0,
  qtdDivergencias: 2,
  qtdAvisos: 5,
};

describe('KpisRateio', () => {
  it('mostra colaboradores, valor final em reais e divergências / avisos', () => {
    render(<KpisRateio {...base} />);
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('R$ 1.500,50')).toBeInTheDocument();
    // "2 / 5": divergências em destaque, avisos ao lado.
    expect(screen.getByText('/ 5')).toBeInTheDocument();
    expect(screen.getByText('/ 5').parentElement).toHaveTextContent('2 / 5');
  });

  it('sem estornos não mostra a composição do valor final', () => {
    render(<KpisRateio {...base} />);
    expect(screen.queryByText(/estornos/)).not.toBeInTheDocument();
  });

  it('com estornos explica o valor final como rateado + estornos', () => {
    render(<KpisRateio {...base} valorRateado={1620.5} totalEstornos={-120} valorFinal={1500.5} />);
    expect(screen.getByText('R$ 1.500,50')).toBeInTheDocument();
    expect(screen.getByText('rateado R$ 1.620,50 + estornos -R$ 120,00')).toBeInTheDocument();
  });
});
