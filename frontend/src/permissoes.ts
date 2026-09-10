import { Usuario, Modulo, NivelArea } from './api';

/**
 * Camada ÚNICA de derivação de papel no frontend (RBAC-lite, por papel).
 *
 * Espelha o backend (`app/auth/service.py`): admin global ⇔ `areas` contém `"*"`;
 * o nível por área vem de `niveis[area]` (default "operador"). O BACKEND continua
 * sendo o dono da segurança (os endpoints já gateiam) — esta camada é só UX
 * (esconder/desabilitar menus, seções e botões), sem duplicar a regra em cada tela.
 */

export function ehAdmin(usuario: Usuario): boolean {
  return usuario.areas.includes('*');
}

/** Admin de QUALQUER área (edita cadastros de área, não a Organização). */
export function ehAdminAreaQualquer(usuario: Usuario): boolean {
  return Object.values(usuario.niveis).includes('admin_area');
}

export function podeEditarCadastro(usuario: Usuario): boolean {
  return ehAdmin(usuario) || ehAdminAreaQualquer(usuario);
}

/** Nível do usuário para um rateio; usa `Modulo.area` como de-para tipo→área. */
export function nivelDoTipo(
  usuario: Usuario,
  tipo: string,
  modulos: Modulo[],
): 'admin' | NivelArea | null {
  if (ehAdmin(usuario)) return 'admin';
  const area = modulos.find((m) => m.tipo === tipo)?.area;
  if (!area || !usuario.areas.includes(area)) return null;
  return usuario.niveis[area] ?? 'operador';
}

/** Pode auditar (ver salário/teto) um rateio. */
export function podeAuditar(usuario: Usuario, tipo: string, modulos: Modulo[]): boolean {
  const n = nivelDoTipo(usuario, tipo, modulos);
  return n === 'admin' || n === 'admin_area';
}
