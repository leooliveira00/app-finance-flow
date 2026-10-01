import { describe, expect, it } from 'vitest';
import type { CentroCusto } from '../../api';
import { LIMITE_LISTA_CC, filtrarCentros } from './centrosCusto';

const cc = (id: number, codigo: string, nome: string): CentroCusto => ({
  id,
  codigo,
  nome,
  empresa: 'Vertex',
});

const CENTROS = [
  cc(1, '206010101', 'Tecnologia da Informação'),
  cc(2, '206010102', 'Recursos Humanos'),
  cc(3, '306020201', 'Financeiro'),
];

describe('filtrarCentros', () => {
  it('sem busca devolve todos, na ordem do cadastro', () => {
    expect(filtrarCentros(CENTROS, '')).toEqual(CENTROS);
    expect(filtrarCentros(CENTROS, '   ')).toEqual(CENTROS);
  });

  it('busca por trecho do código', () => {
    expect(filtrarCentros(CENTROS, '2060101').map((c) => c.id)).toEqual([1, 2]);
  });

  it('busca por nome sem diferenciar maiúsculas e ignorando espaços nas pontas', () => {
    expect(filtrarCentros(CENTROS, '  RECURSOS ').map((c) => c.id)).toEqual([2]);
  });

  it('não encontra nada quando nenhum código ou nome casa', () => {
    expect(filtrarCentros(CENTROS, 'marketing')).toEqual([]);
  });

  it(`limita a lista a ${LIMITE_LISTA_CC} itens para não renderizar o cadastro inteiro`, () => {
    const muitos = Array.from({ length: LIMITE_LISTA_CC + 15 }, (_, i) =>
      cc(i, String(100000 + i), `Centro ${i}`),
    );
    const semBusca = filtrarCentros(muitos, '');
    expect(semBusca).toHaveLength(LIMITE_LISTA_CC);
    expect(semBusca[0].id).toBe(0); // corta o fim, não o começo
    // O limite vale também depois do filtro.
    expect(filtrarCentros(muitos, 'centro')).toHaveLength(LIMITE_LISTA_CC);
  });

  it('não altera a lista recebida', () => {
    const copia = [...CENTROS];
    filtrarCentros(CENTROS, 'rec');
    expect(CENTROS).toEqual(copia);
  });
});
