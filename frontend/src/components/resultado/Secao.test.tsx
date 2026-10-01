import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import Secao from './Secao';

describe('Secao', () => {
  it('nasce fechada: mostra título e contador, mas não o conteúdo', () => {
    render(
      <Secao titulo="Divergências" contador={3}>
        <p>conteúdo da seção</p>
      </Secao>,
    );
    expect(screen.getByText('Divergências')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.queryByText('conteúdo da seção')).not.toBeInTheDocument();
  });

  it('abre e fecha ao clicar no cabeçalho', async () => {
    const user = userEvent.setup();
    render(
      <Secao titulo="Avisos">
        <p>conteúdo da seção</p>
      </Secao>,
    );
    await user.click(screen.getByText('Avisos'));
    expect(screen.getByText('conteúdo da seção')).toBeInTheDocument();
    await user.click(screen.getByText('Avisos'));
    expect(screen.queryByText('conteúdo da seção')).not.toBeInTheDocument();
  });

  it('com defaultAberto já mostra o conteúdo', () => {
    render(
      <Secao titulo="Rateio por Centro de Custo" defaultAberto>
        <p>conteúdo da seção</p>
      </Secao>,
    );
    expect(screen.getByText('conteúdo da seção')).toBeInTheDocument();
  });

  it('sem contador não mostra o selo (zero continua sendo mostrado)', () => {
    const { rerender } = render(
      <Secao titulo="Sem contador">
        <p />
      </Secao>,
    );
    expect(screen.queryByText('0')).not.toBeInTheDocument();
    rerender(
      <Secao titulo="Sem contador" contador={0}>
        <p />
      </Secao>,
    );
    expect(screen.getByText('0')).toBeInTheDocument();
  });
});
