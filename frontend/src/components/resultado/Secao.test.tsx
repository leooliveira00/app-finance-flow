import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import Secao from './Secao';

const cabecalho = (titulo: string) => screen.getByRole('button', { name: new RegExp(titulo) });

describe('Secao', () => {
  it('nasce fechada: mostra título e contador, mas não o conteúdo', () => {
    render(
      <Secao titulo="Divergências" contador={3}>
        <p>conteúdo da seção</p>
      </Secao>,
    );
    expect(screen.getByRole('heading', { level: 3, name: /Divergências/ })).toBeInTheDocument();
    expect(cabecalho('Divergências')).toHaveAttribute('aria-expanded', 'false');
    expect(cabecalho('Divergências')).toHaveTextContent('3');
    expect(screen.queryByText('conteúdo da seção')).not.toBeInTheDocument();
  });

  it('abre e fecha ao clicar no cabeçalho, refletindo o estado em aria-expanded', async () => {
    const user = userEvent.setup();
    render(
      <Secao titulo="Avisos">
        <p>conteúdo da seção</p>
      </Secao>,
    );
    await user.click(cabecalho('Avisos'));
    expect(cabecalho('Avisos')).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('conteúdo da seção')).toBeInTheDocument();

    await user.click(cabecalho('Avisos'));
    expect(cabecalho('Avisos')).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('conteúdo da seção')).not.toBeInTheDocument();
  });

  it('abre pelo teclado: Tab até o cabeçalho, Enter abre e Espaço fecha', async () => {
    const user = userEvent.setup();
    render(
      <Secao titulo="Avisos">
        <p>conteúdo da seção</p>
      </Secao>,
    );
    await user.tab();
    expect(cabecalho('Avisos')).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(screen.getByText('conteúdo da seção')).toBeInTheDocument();
    await user.keyboard(' ');
    expect(screen.queryByText('conteúdo da seção')).not.toBeInTheDocument();
  });

  it('aberta, o cabeçalho aponta para a região de conteúdo (aria-controls)', () => {
    render(
      <Secao titulo="Rateio por Centro de Custo" defaultAberto>
        <p>conteúdo da seção</p>
      </Secao>,
    );
    const id = cabecalho('Rateio por Centro de Custo').getAttribute('aria-controls');
    expect(id).toBeTruthy();
    expect(document.getElementById(id!)).toHaveTextContent('conteúdo da seção');
  });

  it('fechada, não aponta para um conteúdo que não está montado', () => {
    render(
      <Secao titulo="Avisos">
        <p />
      </Secao>,
    );
    expect(cabecalho('Avisos')).not.toHaveAttribute('aria-controls');
  });

  it('sem contador não mostra o selo (zero continua sendo mostrado)', () => {
    const { rerender } = render(
      <Secao titulo="Sem contador">
        <p />
      </Secao>,
    );
    expect(cabecalho('Sem contador')).toHaveTextContent(/^Sem contador$/);
    rerender(
      <Secao titulo="Sem contador" contador={0}>
        <p />
      </Secao>,
    );
    expect(cabecalho('Sem contador')).toHaveTextContent('Sem contador0');
  });
});
