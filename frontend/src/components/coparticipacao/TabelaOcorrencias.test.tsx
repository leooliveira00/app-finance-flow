import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { OcorrenciaCopart } from '../../api';
import TabelaOcorrencias from './TabelaOcorrencias';

const ocorrencia = (o: Partial<OcorrenciaCopart>): OcorrenciaCopart => ({
  beneficiario: 'ANA LIMA',
  data: '2026-07-10',
  procedimento: 'CONSULTA ELETIVA',
  tipo: 'consulta',
  valor: '20.00',
  classificado: true,
  ...o,
});

/** Linhas do corpo da tabela (sem o cabeçalho). */
function linhas() {
  return screen.getAllByRole('row').slice(1);
}

describe('TabelaOcorrencias', () => {
  it('uma linha por evento, com data, beneficiário, procedimento, tipo e valor', () => {
    render(
      <TabelaOcorrencias
        ocorrencias={[
          ocorrencia({}),
          ocorrencia({ beneficiario: 'LUCAS LIMA', tipo: 'especial', valor: '50.00' }),
        ]}
      />,
    );
    const [primeira, segunda] = linhas();
    expect(linhas()).toHaveLength(2);
    expect(within(primeira).getByText('2026-07-10')).toBeInTheDocument();
    expect(within(primeira).getByText('CONSULTA ELETIVA')).toBeInTheDocument();
    expect(within(primeira).getByText('consulta')).toBeInTheDocument();
    expect(within(primeira).getByText('R$ 20,00')).toBeInTheDocument();
    expect(within(segunda).getByText('LUCAS LIMA')).toBeInTheDocument();
    expect(within(segunda).getByText('R$ 50,00')).toBeInTheDocument();
  });

  it('marca o procedimento não classificado e mostra traço no tipo', () => {
    render(
      <TabelaOcorrencias
        ocorrencias={[
          ocorrencia({}),
          ocorrencia({ procedimento: 'EXAME X', tipo: '', valor: '0', classificado: false }),
        ]}
      />,
    );
    const [classificada, naoClassificada] = linhas();
    expect(within(classificada).queryByText('não mapeado')).not.toBeInTheDocument();
    expect(within(naoClassificada).getByText('não mapeado')).toBeInTheDocument();
    expect(within(naoClassificada).getByText('—')).toBeInTheDocument();
  });

  it('sem eventos mostra a mensagem de lista vazia', () => {
    render(<TabelaOcorrencias ocorrencias={[]} />);
    expect(screen.getByText('Nenhuma ocorrência registrada.')).toBeInTheDocument();
    expect(linhas()).toHaveLength(1); // só a linha da mensagem
  });

  it('evento sem data mostra traço na data', () => {
    render(<TabelaOcorrencias ocorrencias={[ocorrencia({ data: '' })]} />);
    expect(within(linhas()[0]).getAllByText('—')).toHaveLength(1);
  });
});
