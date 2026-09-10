/**
 * Cliente da API do backend (FastAPI).
 *
 * Todas as chamadas usam caminhos relativos `/api/...` — em dev o proxy do vite
 * encaminha ao backend; em produção o nginx faz o mesmo. O token JWT é guardado
 * em sessionStorage (a sessão termina ao fechar a guia) e enviado como Bearer.
 */

const TOKEN_KEY = 'financeflow_token';

// ---- Tipos ----
/** Nível do usuário por área. Admin global tem `areas: ['*']` e `niveis: {}`. */
export type NivelArea = 'operador' | 'admin_area';

export interface Usuario {
  email: string; // credencial de login
  nome: string;
  areas: string[];
  /** Mapa {nomeArea: nivel} para não-admins; vazio para admin global. */
  niveis: Record<string, NivelArea>;
  /**
   * Ambiente da base de ESCRITA do Protheus ('teste' | 'producao'). Enquanto for
   * 'teste', os lançamentos NÃO vão para a base oficial e a UI avisa.
   */
  erpAmbiente: string;
}

export interface Modulo {
  tipo: string;
  /** Rótulo curto para UI (ex.: "Mensalidade UNIMED — Pagamento"). */
  nome: string;
  descricao: string;
  area: string;
}

/** Nome amigável do rateio por tipo (espelha o `nome` do backend). Usado onde só
 *  há o `tipo` (histórico, fluxo de execução); fallback = slug capitalizado. */
export const NOME_RATEIO: Record<string, string> = {
  // "Desconto" e "Fatura" separam as duas coparticipações: uma desconta do
  // colaborador na folha (GPE), a outra paga a operadora (AE com NF e boleto).
  // Confundi-las na seleção significa lançar na rotina errada.
  'coparticipacao-plano-saude': 'Desconto de coparticipação',
  'pagamento-unimed': 'Mensalidade Unimed',
  'pagamento-bradesco': 'Mensalidade Bradesco',
  'pagamento-coparticipacao-unimed': 'Fatura de coparticipação Unimed',
  'pagamento-claro': 'Telefonia Claro',
};
export function nomeRateio(tipo: string): string {
  return NOME_RATEIO[tipo] ?? tipo.split('-').map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join(' ');
}

/** Rateios que lançam no ERP — espelha `lanca_no_erp` do backend. Fonte única no
 *  front; mantenha em sincronia ao criar um rateio. */
const TIPOS_LANCA_ERP = new Set<string>([
  'pagamento-unimed',
  'pagamento-bradesco',
  'pagamento-coparticipacao-unimed',
  'pagamento-claro',
  // Desconto em folha (rotina GPE): lança sem gerar título.
  'coparticipacao-plano-saude',
]);
export function lancaNoErp(tipo: string): boolean {
  return TIPOS_LANCA_ERP.has(tipo);
}

/** Rateios que notificam o dep. fiscal após o envio — espelha `notifica_fiscal`.
 *  Lançar no ERP NÃO implica notificar: telefonia e coparticipação não têm NF. */
const TIPOS_NOTIFICA_FISCAL = new Set<string>([
  'pagamento-unimed',
  'pagamento-bradesco',
  'pagamento-coparticipacao-unimed',
  // Telefonia: um e-mail ao fiscal com todos os boletos e títulos, ao final.
  'pagamento-claro',
]);
export function notificaFiscal(tipo: string): boolean {
  return TIPOS_NOTIFICA_FISCAL.has(tipo);
}

/** Rateios em que a unidade do lançamento é o DOCUMENTO, não a empresa: um
 *  título (Autorização de Entrega) por boleto, todos na mesma empresa. Espelha
 *  a capacidade `titulos_erp` do backend. */
const TIPOS_TITULO_POR_DOCUMENTO = new Set<string>(['pagamento-claro']);
export function umTituloPorDocumento(tipo: string): boolean {
  return TIPOS_TITULO_POR_DOCUMENTO.has(tipo);
}

/** Quantos documentos (boletos) este rateio lança um a um. 0 quando o processo
 *  lança por empresa, caso em que não há contagem a exibir. */
export function qtdDocumentos(tipo: string, snapshot: Resultado | null | undefined): number {
  if (!umTituloPorDocumento(tipo) || !snapshot) return 0;
  const boletos = (snapshot as unknown as { boletos?: unknown[] }).boletos;
  return Array.isArray(boletos) ? boletos.length : 0;
}

/** Rateios de desconto em folha: exigem a competência da FOLHA no envio ao ERP
 *  (distinta da competência dos eventos). Espelha `gerar_payload_erp` no backend. */
export function exigeCompetenciaPagamento(tipo: string): boolean {
  return tipo === TIPO_COPARTICIPACAO;
}

/** Uma vida/registro cobrado (titular ou dependente) que compõe o valor do titular. */
export interface VidaResultado {
  nome: string;
  cpf: string;
  valor: string;
  titular: boolean;
}
export interface ItemResultado {
  operadora: string;
  competencia: string;
  empresa: string;
  cpf: string;
  nome: string;
  centro_custo: string;
  classe_valor: string;
  matricula: string;
  num_vidas: number;
  valor: string;
  situacao: string;
  pj?: boolean;
  /** Detalhamento por vida/registro cobrado (para expandir o titular). */
  vidas?: VidaResultado[];
}

export interface AgregadoResultado {
  operadora: string;
  empresa: string;
  centro_custo: string;
  classe_valor: string;
  num_colaboradores: number;
  valor: string;
}

export interface DivergenciaResultado {
  tipo: string;
  operadora: string;
  referencia: string;
  descricao: string;
  valor: string;
  num_vidas: number;
  nome: string;
  empresa: string;
}

export interface ReconciliacaoResultado {
  operadora: string;
  empresa: string | null;
  valor_documento: string;
  valor_base: string;
  diferenca: string;
  bate: boolean;
  mensagem: string;
}

export interface EstornoResultado {
  operadora: string;
  referencia: string;
  valor: string;
  num_vidas: number;
  empresa: string;
}

export interface TotaisResultado {
  operadora: string;
  rateado: string;
  estornos: string;
  nao_rateado: string;
  total: string;
}

// Ajuste manual de realocação (auditoria): move um colaborador de um centro de
// custo/classe para outro, preservando o total da empresa. Fica no snapshot.
export interface AjusteRateio {
  cpf: string;
  nome: string;
  empresa: string;
  de_cc: string;
  de_classe: string;
  para_cc: string;
  para_classe: string;
  valor: string;
}

export interface Resultado {
  itens: ItemResultado[];
  agregado: AgregadoResultado[];
  divergencias: DivergenciaResultado[];
  estornos: EstornoResultado[];
  reconciliacao: ReconciliacaoResultado[];
  totais: TotaisResultado[];
  avisos: string[];
  ajustes?: AjusteRateio[];
}

export interface RespostaProcessamento {
  tipo: string;
  alertas_validacao: string[];
  total_itens: number;
  /** Pode ver dados de auditoria (salário/teto). Operador = false. */
  pode_auditar?: boolean;
  resultado: Resultado;
}

// ---- Coparticipação (resumo com formato próprio) ----
export interface OcorrenciaCopart {
  beneficiario: string;
  data: string;
  procedimento: string;
  tipo: string;
  valor: string;
  classificado: boolean;
}
export interface ItemCopartResultado {
  cpf: string;
  nome: string;
  matricula: string;
  /** Filial do colaborador na API do Protheus (ex.: "01") — usada na integração ERP. */
  filial: string;
  /** Operadora de origem dos eventos ("unimed" | "bradesco") — define o cód. fornecedor no ERP. */
  operadora: string;
  empresa: string;
  /** Dado de auditoria: só presente para admin_area/admin (redigido p/ operador). */
  salario?: string;
  faixa: string;
  num_eventos: number;
  valor_bruto: string;
  /** Dado de auditoria: só presente para admin_area/admin (redigido p/ operador). */
  teto?: string;
  valor_descontado: string;
  teto_aplicado: boolean;
  por_tipo: Record<string, string>;
  ocorrencias: OcorrenciaCopart[];
  pj: boolean;
  /** Fora do lançamento automático em folha — exige tratativa manual (PJ ou teto). */
  bloqueado_envio?: boolean;
  /** Por quê ficou de fora (texto pronto para exibir). */
  motivo_bloqueio?: string;
}
export interface DivergenciaCopartResultado {
  tipo: string;
  cpf: string;
  nome: string;
  descricao: string;
  num_eventos: number;
}
export interface ResultadoCopart {
  itens: ItemCopartResultado[];
  divergencias: DivergenciaCopartResultado[];
  avisos: string[];
  total_descontado: string;
}

/** Tipo do rateio de coparticipação (usado para escolher a tela de resultado). */
export const TIPO_COPARTICIPACAO = 'coparticipacao-plano-saude';

/** Acessa o resultado da coparticipação a partir da resposta genérica. */
export function comoResultadoCopart(resposta: RespostaProcessamento): ResultadoCopart {
  return resposta.resultado as unknown as ResultadoCopart;
}

// ---- Telefonia Claro (um título por boleto; formato próprio) ----
/** Um componente do valor de uma linha: mensalidade do plano ou uso/excedente. */
export interface ServicoLinhaClaro {
  descricao: string;
  categoria: 'mensalidade' | 'uso';
  valor: string;
}
/** Uma linha telefônica do boleto, já casada com o cadastro de telefonia. */
export interface LinhaClaro {
  numero: string;
  numero_exibicao: string;
  centro_custo: string;
  classe_valor: string;
  colaborador_cpf: string;
  colaborador_nome: string;
  /** Conta Claro registrada no cadastro para esta linha ('' = não informada). */
  conta_cadastro: string;
  /** true = a linha foi cobrada num boleto de outra conta (cadastro defasado). */
  conta_divergente: boolean;
  /** false = linha ausente do cadastro. */
  cadastrada: boolean;
  /** Cadastrada E com centro de custo E classe de valor. Só assim vai ao ERP. */
  completa: boolean;
  /** false = cadastrada porém marcada como inativa (e ainda sendo cobrada). */
  ativa: boolean;
  valor: string;
  valor_mensalidades: string;
  valor_uso: string;
  servicos: ServicoLinhaClaro[];
}
export interface CentroCustoClaro {
  centro_custo: string;
  classe_valor?: string;
  qtd_linhas: number;
  /** Valor final do item, já com o ajuste da conta rateado. */
  valor: string;
  /** Soma das linhas do grupo, antes do ajuste. */
  valor_bruto?: string;
  /** Parte do ajuste da conta atribuída a este item (0 quando não há ajuste). */
  ajuste?: string;
}

/** Lançamento da conta que não pertence a nenhuma linha (ex.: crédito anterior). */
export interface AjusteClaro {
  descricao: string;
  valor: string;
}
/** Um boleto = um título a lançar no Contas a Pagar. */
export interface BoletoClaro {
  arquivo: string;
  conta: string;
  cliente: string;
  razao_social: string;
  cnpj_tomador: string;
  competencia: string;
  periodo: string;
  vencimento: string;
  emissao: string;
  linha_digitavel: string;
  nfcom_numero: string;
  nfcom_serie: string;
  nfcom_chave: string;
  /** Total impresso no boleto — é o valor do título. */
  valor_total: string;
  valor_linhas: string;
  diferenca: string;
  confere: boolean;
  qtd_linhas: number;
  qtd_incompletas: number;
  qtd_conta_divergente: number;
  valor_incompleto: string;
  /** Lançamentos da conta; vazio na maioria dos boletos. */
  ajustes: AjusteClaro[];
  valor_ajustes: string;
  linhas: LinhaClaro[];
  por_centro_custo: CentroCustoClaro[];
}
/** Linha sem destino contábil completo, agregada entre todos os boletos. */
export interface PendenciaClaro {
  numero: string;
  numero_exibicao: string;
  valor: string;
  /** Rótulos dos boletos onde a linha foi cobrada (conta, ou o arquivo). */
  boletos: string[];
  /** Contas Claro reais onde a linha apareceu — uma só = preenche o cadastro. */
  contas: string[];
  /** true = já existe no cadastro, só falta completar centro de custo/classe. */
  cadastrada: boolean;
  /** false = linha cobrada a R$ 0 neste boleto; aparece, mas não trava o envio. */
  bloqueia: boolean;
  centro_custo: string;
  classe_valor: string;
  colaborador_nome: string;
}
/** Contas contábeis fixas do processo (iguais para todas as linhas). */
export interface ContabilClaro {
  conta_debito: string;
  conta_credito: string;
}
export interface ResultadoClaro {
  boletos: BoletoClaro[];
  pendencias: PendenciaClaro[];
  contabil: ContabilClaro;
  /** Motivos que impedem o lançamento, em texto pronto para exibir. */
  bloqueios: string[];
  /** true enquanto houver qualquer bloqueio — trava o envio ao ERP. */
  bloqueado: boolean;
  totais: {
    qtd_boletos: number;
    valor_total: string;
    qtd_linhas: number;
    qtd_incompletas: number;
    /** Subconjunto de `qtd_incompletas` que realmente trava o lançamento. */
    qtd_bloqueantes: number;
    qtd_conta_divergente: number;
    valor_incompleto: string;
  };
  por_centro_custo: CentroCustoClaro[];
}

/** Tipo do rateio de telefonia (usado para escolher a tela de resultado). */
export const TIPO_CLARO = 'pagamento-claro';

/** Acessa o resultado da telefonia a partir da resposta genérica. */
export function comoResultadoClaro(resposta: RespostaProcessamento): ResultadoClaro {
  return resposta.resultado as unknown as ResultadoClaro;
}

// ---- Token ----
// A sessão vive na GUIA: `sessionStorage` é descartado pelo navegador ao fechar a
// aba/janela, então fechar a guia encerra a sessão. Antes o token ficava em
// `localStorage` e sobrevivia a fechar o navegador e reabrir dias depois — numa
// máquina compartilhada, isso deixa a sessão aberta para o próximo que usar.
export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}
export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  // Resquício das versões que guardavam em localStorage.
  localStorage.removeItem(TOKEN_KEY);
}

// Descarta na carga um token deixado em localStorage por versão anterior: sem
// isto ele ficaria guardado no navegador indefinidamente, sem uso e sem expirar.
localStorage.removeItem(TOKEN_KEY);

// ---- Erro de API ----
export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function extrairErro(resp: Response): Promise<ApiError> {
  let detail: unknown;
  let mensagem = `Erro ${resp.status}`;
  try {
    const corpo = await resp.json();
    detail = corpo?.detail ?? corpo;
    if (typeof detail === 'string') mensagem = detail;
  } catch {
    /* corpo não-JSON */
  }
  return new ApiError(mensagem, resp.status, detail);
}

async function request(path: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const resp = await fetch(path, { ...options, headers });
  if (resp.status === 401) {
    clearToken();
    throw new ApiError('Sessão expirada. Faça login novamente.', 401);
  }
  if (!resp.ok) throw await extrairErro(resp);
  return resp;
}

// ---- Endpoints ----
/** Sessão a partir da resposta de /auth (login, GET /me e PUT /me têm a mesma forma). */
function paraUsuario(data: {
  email: string;
  nome: string;
  areas: string[];
  niveis?: Record<string, NivelArea>;
  erp_ambiente?: string;
}): Usuario {
  return {
    email: data.email,
    nome: data.nome,
    areas: data.areas,
    niveis: data.niveis ?? {},
    // Sem o campo, assume 'teste': avisar à toa é melhor que deixar de avisar.
    erpAmbiente: data.erp_ambiente ?? 'teste',
  };
}

export async function login(email: string, password: string): Promise<Usuario> {
  // O campo do form OAuth2 se chama "username", mas carrega o e-mail (login por e-mail).
  const body = new URLSearchParams({ username: email, password });
  const resp = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!resp.ok) throw await extrairErro(resp);
  const data = await resp.json();
  setToken(data.access_token);
  return paraUsuario(data);
}

export async function me(): Promise<Usuario> {
  const resp = await request('/api/auth/me');
  const data = await resp.json();
  return paraUsuario(data);
}

/** Autogestão do próprio perfil: nome e/ou troca de senha (não altera o e-mail). */
export interface PerfilUpdate {
  nome?: string;
  senha_atual?: string;
  senha_nova?: string;
}

export async function atualizarPerfil(dados: PerfilUpdate): Promise<Usuario> {
  const resp = await request('/api/auth/me', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(dados),
  });
  const data = await resp.json();
  return paraUsuario(data);
}

// ---- Cadastro da coparticipação ----
export interface CadastroCopartFaixa {
  nome: string;
  salario_inicial: string;
  salario_final: string;
  valores: { consulta: string; simples: string; especial: string };
}
export interface CadastroCopart {
  teto_percentual: string;
  salario_padrao_pj: string;
  faixas: CadastroCopartFaixa[];
}

export async function getCadastroCoparticipacao(): Promise<CadastroCopart> {
  const resp = await request('/api/cadastro/coparticipacao');
  return resp.json();
}

export async function salvarCadastroCoparticipacao(cadastro: CadastroCopart): Promise<CadastroCopart> {
  const resp = await request('/api/cadastro/coparticipacao', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cadastro),
  });
  return resp.json();
}

// ---- Colaboradores PJ ----
export interface ColaboradorPJ {
  cpf: string;
  nome: string;
  centro_custo?: string;
  empresa?: string;
  classe_valor?: string;
}

// Alocação contábil (pagamento) atribuída a um PJ. Opcional: a coparticipação
// não usa; só é enviada ao atribuir um PJ a um centro de custo no pagamento.
export interface AlocacaoPJ {
  centro_custo?: string;
  empresa?: string;
  classe_valor?: string;
}

export async function listarPJ(): Promise<ColaboradorPJ[]> {
  const resp = await request('/api/cadastro/coparticipacao/pj');
  return resp.json();
}

export async function adicionarPJ(cpf: string, nome: string, alocacao?: AlocacaoPJ): Promise<void> {
  await request('/api/cadastro/coparticipacao/pj', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cpf, nome, ...alocacao }),
  });
}

export async function removerPJ(cpf: string): Promise<void> {
  await request(`/api/cadastro/coparticipacao/pj/${encodeURIComponent(cpf)}`, { method: 'DELETE' });
}

// ---- Centros de custo (dicionário código -> nome; cadastro de pagamento) ----
export interface CentroCusto {
  id: number;
  codigo: string;
  nome: string;
  empresa: string;
}

export async function listarCentrosCusto(): Promise<CentroCusto[]> {
  const resp = await request('/api/cadastro/centros-custo');
  return resp.json();
}

export async function criarCentroCusto(codigo: string, nome: string, empresa = ''): Promise<CentroCusto> {
  const resp = await request('/api/cadastro/centros-custo', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ codigo, nome, empresa }),
  });
  return resp.json();
}

export async function atualizarCentroCusto(id: number, codigo: string, nome: string, empresa = ''): Promise<CentroCusto> {
  const resp = await request(`/api/cadastro/centros-custo/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ codigo, nome, empresa }),
  });
  return resp.json();
}

export async function removerCentroCusto(id: number): Promise<void> {
  await request(`/api/cadastro/centros-custo/${id}`, { method: 'DELETE' });
}

// ---- Linhas telefônicas (de-para linha -> centro de custo; cadastro da TI) ----
export interface LinhaTelefonica {
  id: number;
  /** Somente dígitos, com DDD — é como o boleto é lido. */
  numero: string;
  centro_custo: string;
  classe_valor: string;
  /** Conta Claro (nº do boleto) à qual a linha está vinculada. */
  conta: string;
  colaborador_cpf: string;
  colaborador_nome: string;
  ativo: boolean;
  observacao: string;
}
/** Payload de escrita: sem `id`, aceito também na criação em lote. */
export type LinhaTelefonicaIn = Omit<LinhaTelefonica, 'id'>;

/** Contas contábeis fixas da telefonia (não variam por linha nem por CC). */
export interface ParametrosTelefonia {
  conta_debito: string;
  conta_credito: string;
}

export async function getParametrosTelefonia(): Promise<ParametrosTelefonia> {
  const resp = await request('/api/cadastro/linhas-telefonicas/parametros');
  return resp.json();
}

export async function salvarParametrosTelefonia(params: ParametrosTelefonia): Promise<ParametrosTelefonia> {
  const resp = await request('/api/cadastro/linhas-telefonicas/parametros', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  return resp.json();
}

export async function listarLinhasTelefonicas(): Promise<LinhaTelefonica[]> {
  const resp = await request('/api/cadastro/linhas-telefonicas');
  return resp.json();
}

export async function criarLinhaTelefonica(linha: LinhaTelefonicaIn): Promise<LinhaTelefonica> {
  const resp = await request('/api/cadastro/linhas-telefonicas', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(linha),
  });
  return resp.json();
}

export async function atualizarLinhaTelefonica(id: number, linha: LinhaTelefonicaIn): Promise<LinhaTelefonica> {
  const resp = await request(`/api/cadastro/linhas-telefonicas/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(linha),
  });
  return resp.json();
}

export async function removerLinhaTelefonica(id: number): Promise<void> {
  await request(`/api/cadastro/linhas-telefonicas/${id}`, { method: 'DELETE' });
}

/** Importa/atualiza várias linhas de uma vez (upsert por número). */
export async function salvarLinhasTelefonicasEmLote(
  linhas: LinhaTelefonicaIn[],
): Promise<{ criadas: number; atualizadas: number }> {
  const resp = await request('/api/cadastro/linhas-telefonicas/lote', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(linhas),
  });
  return resp.json();
}

// ---- Empresas do grupo (fonte única: rest, CNPJ, rotina no ERP) ----
export interface Empresa {
  id: number;
  nome: string;
  rest: string;
  cnpj: string;
  rotina_erp: string;      // "ae" | "pre_nota"
  prenota_produto: string;
  prenota_filial: string;
}
export type EmpresaInput = Omit<Empresa, 'id'>;

export async function listarEmpresas(): Promise<Empresa[]> {
  const resp = await request('/api/cadastro/empresas');
  return resp.json();
}
export async function salvarEmpresa(body: EmpresaInput, id?: number): Promise<Empresa> {
  const url = id ? `/api/cadastro/empresas/${id}` : '/api/cadastro/empresas';
  const resp = await request(url, {
    method: id ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return resp.json();
}
export async function removerEmpresa(id: number): Promise<void> {
  await request(`/api/cadastro/empresas/${id}`, { method: 'DELETE' });
}

// ---- Fornecedores dos lançamentos no ERP (plano de saúde, telefonia) ----
export interface Fornecedor {
  id: number;
  nome: string; // chave do módulo: "unimed" | "bradesco" | "claro"
  cnpj: string; // CNPJ (formatado); os dígitos p/ o ERP são derivados no backend
}
export type FornecedorInput = Omit<Fornecedor, 'id'>;

export async function listarFornecedores(): Promise<Fornecedor[]> {
  const resp = await request('/api/cadastro/fornecedores');
  return resp.json();
}
export async function salvarFornecedor(body: FornecedorInput, id?: number): Promise<Fornecedor> {
  const url = id ? `/api/cadastro/fornecedores/${id}` : '/api/cadastro/fornecedores';
  const resp = await request(url, {
    method: id ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return resp.json();
}
export async function removerFornecedor(id: number): Promise<void> {
  await request(`/api/cadastro/fornecedores/${id}`, { method: 'DELETE' });
}

// ---- Disponibilidade dos processos (admin) ----
/** Processo inativo sai do painel e não aceita novas execuções; o histórico
 *  dele continua consultável. */
export interface ProcessoStatus {
  tipo: string;
  nome: string;
  descricao: string;
  area: string;
  ativo: boolean;
  atualizado_por: string;
  atualizado_em: string | null;
}

export async function listarProcessos(): Promise<ProcessoStatus[]> {
  const resp = await request('/api/processos');
  return resp.json();
}
export async function definirProcessoAtivo(tipo: string, ativo: boolean): Promise<void> {
  await request(`/api/processos/${encodeURIComponent(tipo)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ativo }),
  });
}

// ---- Execuções (persistência + envio ao ERP + histórico) ----
/** Registro que o ERP recusou, com o motivo já legível. */
export interface PendenteEnvio {
  matricula: string;
  nome: string;
  motivo: string;
}

export interface EnvioErpResultado {
  empresa: string;
  /** Unidade do envio dentro da empresa: vazia no plano de saúde (um título por
   *  empresa); na telefonia é a conta da Claro (um título por boleto). */
  referencia: string;
  rest: string;
  contrato: string;
  titulo: string;
  /** enviando | enviado | parcial | erro | pendente. "enviando" = gravado antes
   *  do POST; se persistir, o envio caiu antes da resposta do ERP. */
  status: string;
  mensagem: string;
  /** Lote da folha: quantos registros foram enviados e quantos o ERP aceitou. */
  enviados?: number;
  aceitos?: number;
  /** Quem o ERP recusou — os ÚNICOS reenviados na próxima tentativa. */
  matriculas_pendentes?: PendenteEnvio[];
}

export interface DocumentoResumo {
  id: number;
  categoria: string;
  nome: string;
  mime: string;
}

/** Uma tentativa de envio ao ERP (log imutável, para o histórico). */
export interface TentativaEnvio {
  id: number;
  empresa: string;
  /** Unidade do envio dentro da empresa (telefonia: a conta da Claro). */
  referencia: string;
  rest: string;
  contrato: string;
  titulo: string;
  status: string; // enviado | erro | pendente | pulado
  mensagem: string;
  usuario: string;
  /** Resposta bruta do ERP nesta tentativa (só nas falhas): mostra o que ele
   *  devolveu, inclusive quando aceita parte do lote sem dizer quais recusou. */
  resposta_erp?: unknown;
  criado_em: string;
}

/**
 * O histórico de tentativas só é relevante quando agrega informação: houve algum
 * erro/pendência OU mais de uma tentativa para alguma empresa (retentativa). Em
 * êxito de primeira (uma tentativa por empresa, todas enviadas), a lista por
 * empresa já mostra os títulos — o histórico seria redundante.
 */
export function historicoRelevante(tentativas: TentativaEnvio[]): boolean {
  if (tentativas.length === 0) return false;
  const houveErro = tentativas.some((t) => t.status !== 'enviado');
  // A unidade do envio é (empresa, referência), não a empresa: na telefonia os
  // N boletos são lançados na MESMA empresa, e contar só a empresa fazia sete
  // lançamentos distintos parecerem seis retentativas — o log aparecia repetindo
  // o que o bloco de envios já mostrava.
  const unidades = new Set(tentativas.map((t) => `${t.empresa}|${t.referencia ?? ''}`));
  const houveRetentativa = unidades.size < tentativas.length;
  return houveErro || houveRetentativa;
}

/** Nº do processo (id da execução) para rastreio, zero-padded (ex.: 023). */
export function processoId(id: number): string {
  return String(id ?? 0).padStart(3, '0');
}

export interface Execucao {
  id: number;
  tipo: string;
  competencia: string;
  usuario: string;
  criado_em: string;
  status: string; // pendente_envio | enviado | erro_envio
  total: string;
  documentos: DocumentoResumo[];
  envios: EnvioErpResultado[];
  tentativas: TentativaEnvio[]; // histórico de tentativas de envio ao ERP
  resultado?: Resultado;
  notificado_em?: string | null; // quando NF/boleto + títulos foram ao dep. fiscal
  /** A quem a notificação foi enviada; ausente nas execuções anteriores ao registro. */
  notificado_para?: { para: string[]; copia: string[] } | null;
  pode_auditar?: boolean; // quem consulta pode ver salário/teto (admin_area/admin)
}

export interface EnvioResposta {
  bloqueado: boolean;
  bloqueios?: string[];
  alertas?: string[];
  status: string;
  envios: EnvioErpResultado[];
  tentativas: TentativaEnvio[];
}

export async function confirmarExecucao(
  tipo: string,
  competencia: string,
  resultado: Resultado,
  arquivos: File[],
): Promise<Execucao> {
  const form = new FormData();
  form.append('tipo', tipo);
  form.append('competencia', competencia);
  form.append('resultado', JSON.stringify(resultado));
  for (const arquivo of arquivos) form.append('arquivos', arquivo);
  const resp = await request('/api/execucoes', { method: 'POST', body: form });
  return resp.json();
}

export async function listarExecucoes(): Promise<Execucao[]> {
  const resp = await request('/api/execucoes');
  return resp.json();
}

export async function getExecucao(id: number): Promise<Execucao> {
  const resp = await request(`/api/execucoes/${id}`);
  return resp.json();
}

/** Envia (ou reenvia) ao ERP. `competenciaPagamento` (AAAAMM) é obrigatória nos
 *  rateios de desconto em folha — ver `exigeCompetenciaPagamento`. */
export async function enviarExecucao(
  id: number,
  competenciaPagamento?: string,
): Promise<EnvioResposta> {
  const resp = await request(`/api/execucoes/${id}/enviar`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ competencia_pagamento: competenciaPagamento ?? null }),
  });
  return resp.json();
}

export interface NotificacaoResposta {
  ok: boolean;
  destinatarios: string[];
  notificado_em: string | null;
}

export async function notificarFiscal(id: number): Promise<NotificacaoResposta> {
  const resp = await request(`/api/execucoes/${id}/notificar-fiscal`, { method: 'POST' });
  return resp.json();
}

export async function baixarDocumentoExecucao(execId: number, docId: number, nome: string): Promise<void> {
  const resp = await request(`/api/execucoes/${execId}/documentos/${docId}`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function getModulos(incluirInativos = false): Promise<Modulo[]> {
  // `incluirInativos` só tem efeito para admin (o backend ignora nos demais):
  // as telas de Configurações precisam ver o processo desativado, porque é nelas
  // que se completa o cadastro para reativá-lo.
  const resp = await request(`/api/modulos${incluirInativos ? '?incluir_inativos=true' : ''}`);
  return resp.json();
}

// ---- Organização (usuários e áreas/setores) — admin ----
/** Vínculo de uma área com o nível do usuário nela. */
export interface AreaNivel {
  area: string;
  nivel: NivelArea;
}

export interface UsuarioOrg {
  id: number;
  email: string;
  nome: string;
  admin: boolean;
  ativo: boolean;
  areas: AreaNivel[];
}

export interface AreaOrg {
  id: number;
  nome: string;
  rateios: string[];
  /** E-mails em cópia nas notificações dos rateios desta área (lista separada
   *  por vírgula). Vazio = a notificação vai só ao departamento fiscal. */
  emails_copia: string;
  num_usuarios: number;
}

export interface RateioDisponivel {
  tipo: string;
  /** Rótulo curto para UI (ex.: "Pagamento UNIMED"). */
  nome: string;
  descricao: string;
}

export interface UsuarioInput {
  email: string;
  nome: string;
  senha: string;
  admin: boolean;
  areas: AreaNivel[];
}

export interface UsuarioUpdateInput {
  nome: string;
  email: string;
  admin: boolean;
  ativo: boolean;
  areas: AreaNivel[];
  senha?: string;
}

export async function listarRateiosDisponiveis(): Promise<RateioDisponivel[]> {
  const resp = await request('/api/organizacao/rateios');
  return resp.json();
}

export async function listarUsuarios(): Promise<UsuarioOrg[]> {
  const resp = await request('/api/organizacao/usuarios');
  return resp.json();
}

export async function criarUsuario(dados: UsuarioInput): Promise<UsuarioOrg> {
  const resp = await request('/api/organizacao/usuarios', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(dados),
  });
  return resp.json();
}

export async function atualizarUsuario(id: number, dados: UsuarioUpdateInput): Promise<UsuarioOrg> {
  const resp = await request(`/api/organizacao/usuarios/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(dados),
  });
  return resp.json();
}

export async function removerUsuario(id: number): Promise<void> {
  await request(`/api/organizacao/usuarios/${id}`, { method: 'DELETE' });
}

export async function listarAreas(): Promise<AreaOrg[]> {
  const resp = await request('/api/organizacao/areas');
  return resp.json();
}

export async function criarArea(
  nome: string, rateios: string[], emailsCopia = '',
): Promise<AreaOrg> {
  const resp = await request('/api/organizacao/areas', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nome, rateios, emails_copia: emailsCopia }),
  });
  return resp.json();
}

export async function atualizarArea(
  id: number, nome: string, rateios: string[], emailsCopia = '',
): Promise<AreaOrg> {
  const resp = await request(`/api/organizacao/areas/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nome, rateios, emails_copia: emailsCopia }),
  });
  return resp.json();
}

// ---- Destinatários das notificações (fiscal + cópia) ----
export interface ConfigNotificacao {
  fiscal_emails: string;
  copia_permanente: string;
  atualizado_por: string;
  atualizado_em: string | null;
}
/** Quem receberá a notificação de um rateio, já resolvido (fiscal + área). */
export interface DestinatariosNotificacao {
  para: string[];
  copia: string[];
  reply_to: string[];
}

export async function obterConfigNotificacao(): Promise<ConfigNotificacao> {
  const resp = await request('/api/notificacoes');
  return resp.json();
}
export async function salvarConfigNotificacao(
  fiscalEmails: string, copiaPermanente: string,
): Promise<ConfigNotificacao> {
  const resp = await request('/api/notificacoes', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fiscal_emails: fiscalEmails, copia_permanente: copiaPermanente }),
  });
  return resp.json();
}
export async function destinatariosNotificacao(tipo: string): Promise<DestinatariosNotificacao> {
  const resp = await request(`/api/notificacoes/destinatarios?tipo=${encodeURIComponent(tipo)}`);
  return resp.json();
}

export async function removerArea(id: number): Promise<void> {
  await request(`/api/organizacao/areas/${id}`, { method: 'DELETE' });
}

export async function processar(
  tipo: string,
  arquivos: File[],
): Promise<RespostaProcessamento> {
  const form = new FormData();
  for (const arquivo of arquivos) form.append('arquivos', arquivo);
  const resp = await request(`/api/rateio/${encodeURIComponent(tipo)}/processar`, {
    method: 'POST',
    body: form,
  });
  return resp.json();
}

export async function baixarCsv(tipo: string): Promise<void> {
  const resp = await request(`/api/rateio/${encodeURIComponent(tipo)}/resultado.csv`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `rateio_${tipo}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/**
 * Baixa o TXT de redundância p/ importação manual no ERP (fallback ao envio via
 * API). `competencia` no formato AAAAMM (ex.: "202607"). `empresa` (opcional)
 * filtra os colaboradores de uma única empresa (ex.: "Vertex", "Zenith").
 */
/** Exportações do HISTÓRICO: leem o snapshot da execução, não o último
 *  processamento em memória — no histórico a fonte tem de ser a execução aberta. */
/** Seções exportáveis do snapshot de uma execução (espelha SECOES_CSV no backend). */
export type SecaoExecucao =
  | 'itens' | 'agregado' | 'reconciliacao' | 'divergencias' | 'estornos' | 'totais';

export async function baixarCsvExecucao(id: number, secao: SecaoExecucao = 'itens'): Promise<void> {
  const resp = await request(`/api/execucoes/${id}/resultado.csv?secao=${secao}`);
  await salvarArquivo(resp, `${secao}_${id}.csv`);
}

export async function baixarPjCsvExecucao(id: number): Promise<void> {
  const resp = await request(`/api/execucoes/${id}/pj.csv`);
  await salvarArquivo(resp, `pj_${id}.csv`);
}

/** Dispara o download de uma resposta como arquivo. */
async function salvarArquivo(resp: Response, nome: string): Promise<void> {
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** CSV dos PJs (nome, CPF, operadora, valor): eles não entram no lançamento em
 *  folha — o desconto é cobrado na nota, em processo manual. */
export async function baixarPjCsv(tipo: string): Promise<void> {
  const resp = await request(`/api/rateio/${encodeURIComponent(tipo)}/pj.csv`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `pj_${tipo}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function baixarTxt(tipo: string, competencia: string, empresa?: string): Promise<void> {
  let url = `/api/rateio/${encodeURIComponent(tipo)}/resultado.txt?competencia=${encodeURIComponent(competencia)}`;
  if (empresa) url += `&empresa=${encodeURIComponent(empresa)}`;
  const resp = await request(url);
  const blob = await resp.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = empresa
    ? `rateio_${tipo}_${empresa}_${competencia}.txt`
    : `rateio_${tipo}_${competencia}.txt`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}
