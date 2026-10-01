import { describe, expect, it } from 'vitest';
import { rotuloOperadora } from './rotulos';

describe('rotuloOperadora', () => {
  it('traduz o código da operadora, sem diferenciar maiúsculas', () => {
    expect(rotuloOperadora('unimed')).toBe('Unimed');
    expect(rotuloOperadora('BRADESCO')).toBe('Bradesco');
  });

  it('operadora desconhecida aparece como veio, para não esconder o dado', () => {
    expect(rotuloOperadora('amil')).toBe('amil');
  });

  it('sem operadora mostra um traço', () => {
    expect(rotuloOperadora('')).toBe('—');
  });
});
