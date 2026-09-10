import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  AlertTriangle, ArrowLeft, Banknote, Building2, CalendarDays, CheckCircle2,
  ChevronRight, FileDown, FileText, Loader2, Phone, Plus, Smartphone, X,
} from 'lucide-react';
import * as api from '../api';
import { ApiError, BoletoClaro, LinhaClaro, RespostaProcessamento, comoResultadoClaro } from '../api';
import { Toast } from '../types';

interface Props {
  tipo: string;
  competence: string;
  resposta: RespostaProcessamento;
  onBackToFlow: () => void;
  onConfirmSend: () => void;
  onReprocessar: () => Promise<void>;
  addToast: (message: string, type: Toast['type']) => void;
  /** Modo leitura (consulta no histórico): esconde ações de escrita. */
  somenteLeitura?: boolean;
  /** Conta do boleto -> nº do título lançado no ERP (consulta do histórico). */
  titulosPorConta?: Record<string, string>;
}

function moeda(valor: string | number): string {
  return Number(valor || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

/** Soma valores que chegam como string do backend (Decimal serializado). */
/** Chave do destino contábil: centro de custo + classe de valor. */
function destinoChave(centroCusto: string, classeValor?: string): string {
  return `${centroCusto}|${classeValor ?? ''}`;
}

function somar(valores: Array<string | number>): number {
  return valores.reduce<number>((acc, v) => acc + Number(v || 0), 0);
}

function data(iso: string): string {
  if (!iso) return '—';
  const [ano, mes, dia] = iso.split('-');
  return dia ? `${dia}/${mes}/${ano}` : iso;
}

function Cartao({ icone: Icone, rotulo, valor, destaque }: {
  icone: typeof Phone; rotulo: string; valor: string; destaque?: 'alerta' | 'ok';
}) {
  const cor = destaque === 'alerta' ? 'text-amber-600' : destaque === 'ok' ? 'text-emerald-600' : 'text-slate-900';
  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-4 flex items-center gap-3">
      <div className="h-9 w-9 rounded-xl bg-slate-100 flex items-center justify-center shrink-0">
        <Icone className="h-4 w-4 text-slate-500" />
      </div>
      <div className="min-w-0">
        <p className="text-[11px] uppercase tracking-wide text-slate-500 font-semibold">{rotulo}</p>
        <p className={`text-lg font-bold leading-tight truncate ${cor}`}>{valor}</p>
      </div>
    </div>
  );
}

// `key` é declarado aqui porque o projeto não usa @types/react — sem eles o
// TS não reconhece a prop especial do JSX (mesmo padrão de ToastNotification).
interface LinhaDetalheProps {
  key?: string;
  linha: LinhaClaro;
  /** Código -> nome do centro de custo; '' quando não está no dicionário. */
  nomeCentro: (codigo: string) => string;
  /** Há excedente em algum lugar deste boleto? Define se a quebra é exibida. */
  detalharExcedente: boolean;
}

/** Uma linha da tabela do boleto; expande para mostrar a composição do valor. */
function LinhaDetalhe({ linha, nomeCentro, detalharExcedente }: LinhaDetalheProps) {
  const [aberto, setAberto] = useState(false);
  return (
    <>
      <tr
        className={`border-t border-slate-100 cursor-pointer hover:bg-slate-50 ${linha.completa ? '' : 'bg-amber-50/60'}`}
        onClick={() => setAberto((a) => !a)}
      >
        <td className="px-4 py-2">
          <div className="flex items-center gap-2">
            <ChevronRight className={`h-3.5 w-3.5 text-slate-400 transition-transform ${aberto ? 'rotate-90' : ''}`} />
            <span className="font-medium text-slate-800">{linha.numero_exibicao}</span>
          </div>
        </td>
        <td className="px-4 py-2 text-slate-600">{linha.colaborador_nome || '—'}</td>
        <td className="px-4 py-2">
          {linha.completa ? (
            // O nome do CC vai no title: a coluna é estreita e são dezenas de
            // linhas — exibi-lo em toda linha viraria ruído.
            <span className="font-medium text-slate-800" title={nomeCentro(linha.centro_custo)}>
              {linha.centro_custo}
              <span className="ml-1.5 text-slate-400">/ {linha.classe_valor}</span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full">
              <AlertTriangle className="h-3 w-3" />
              {!linha.cadastrada
                ? 'sem cadastro'
                : !linha.centro_custo
                  ? 'sem centro de custo'
                  : 'sem classe de valor'}
            </span>
          )}
          {linha.cadastrada && !linha.ativa && (
            <span className="ml-2 text-[11px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">inativa</span>
          )}
          {linha.conta_divergente && (
            <span
              className="ml-2 text-[11px] font-semibold text-sky-700 bg-sky-100 px-2 py-0.5 rounded-full"
              title={`Cadastrada na conta ${linha.conta_cadastro}. A linha migrou de boleto.`}
            >
              mudou de conta
            </span>
          )}
        </td>
        {detalharExcedente && (
          <>
            <td className="px-4 py-2 text-right tabular-nums text-slate-600">{moeda(linha.valor_mensalidades)}</td>
            <td className={`px-4 py-2 text-right tabular-nums ${Number(linha.valor_uso) > 0 ? 'text-amber-700 font-semibold' : 'text-slate-400'}`}>
              {moeda(linha.valor_uso)}
            </td>
          </>
        )}
        <td className="px-4 py-2 text-right tabular-nums font-semibold text-slate-900">{moeda(linha.valor)}</td>
      </tr>
      {aberto && (
        <tr className="bg-slate-50/70">
          <td colSpan={detalharExcedente ? 6 : 4} className="px-4 py-3">
            <p className="text-[11px] uppercase tracking-wide text-slate-500 font-semibold mb-2">
              Serviços que compõem o valor
            </p>
            {/* Uma coluna só: em duas, a descrição de um serviço encostava no
                valor do serviço da coluna vizinha e não dava para saber qual
                valor pertencia a qual descrição. */}
            <div className="flex flex-col gap-1 max-w-2xl">
              {linha.servicos.map((servico, i) => (
                <div key={i} className="flex items-baseline gap-3 text-xs">
                  <span className="text-slate-600">
                    {servico.categoria === 'uso' && (
                      <span className="mr-1.5 text-[10px] font-bold uppercase text-amber-700">uso</span>
                    )}
                    {servico.descricao}
                  </span>
                  {/* Pontilhado ligando descrição e valor: o olho não se perde
                      quando as descrições têm comprimentos muito diferentes. */}
                  <span className="flex-1 border-b border-dotted border-slate-300 translate-y-[-0.2rem]" />
                  <span className={`tabular-nums shrink-0 ${Number(servico.valor) > 0 ? 'text-slate-800 font-medium' : 'text-slate-400'}`}>
                    {moeda(servico.valor)}
                  </span>
                </div>
              ))}
              <div className="flex items-baseline gap-3 text-xs pt-1.5 mt-0.5 border-t border-slate-200">
                <span className="font-semibold text-slate-700">Total da linha</span>
                <span className="flex-1" />
                <span className="tabular-nums shrink-0 font-bold text-slate-900">{moeda(linha.valor)}</span>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

interface CartaoBoletoProps {
  key?: string;
  boleto: BoletoClaro;
  /** Código -> nome do centro de custo; '' quando não está no dicionário. */
  nomeCentro: (codigo: string) => string;
  /** Título gerado no ERP para este boleto ('' antes do lançamento). */
  titulo?: string;
}

/**
 * Um boleto = um título no Contas a Pagar.
 *
 * Nasce COLAPSADO: numa execução com 8 boletos, abrir tudo joga centenas de
 * linhas na tela e some com a visão geral. O cabeçalho carrega o que decide se
 * vale abrir (valor, vencimento, se fecha, se há pendência); o resto é auditoria
 * sob demanda.
 */
function CartaoBoleto({ boleto, nomeCentro, titulo }: CartaoBoletoProps) {
  const [aberto, setAberto] = useState(false);
  // Sem nenhum excedente no boleto, "Mensalidade" repetiria "Total" em todas as
  // linhas. As colunas só aparecem quando há o que comparar.
  const detalharExcedente = boleto.linhas.some((l) => Number(l.valor_uso) > 0);
  const temAjustes = boleto.ajustes.length > 0;
  const colunas = detalharExcedente ? 6 : 4;
  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
      <button
        onClick={() => setAberto((a) => !a)}
        aria-expanded={aberto}
        className="w-full text-left p-5 hover:bg-slate-50/70 transition-colors cursor-pointer"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <ChevronRight className={`h-4 w-4 text-slate-400 shrink-0 transition-transform ${aberto ? 'rotate-90' : ''}`} />
              <FileText className="h-4 w-4 text-slate-400 shrink-0" />
              <h3 className="text-sm font-bold text-slate-900">Conta {boleto.conta || '—'}</h3>
              {/* Título do ERP no próprio boleto: é a ligação entre o documento e
                  o lançamento, e é a pergunta que se faz ao consultar o histórico. */}
              {titulo && (
                <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full font-mono">
                  Título {titulo}
                </span>
              )}
              {boleto.confere ? (
                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full">
                  <CheckCircle2 className="h-3 w-3" /> confere
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-rose-700 bg-rose-100 px-2 py-0.5 rounded-full">
                  <AlertTriangle className="h-3 w-3" /> diferença de {moeda(boleto.diferenca)}
                </span>
              )}
              {boleto.qtd_incompletas > 0 && (
                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full">
                  <AlertTriangle className="h-3 w-3" /> {boleto.qtd_incompletas} pendente(s)
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-1 ml-6 truncate">{boleto.arquivo}</p>
          </div>
          <div className="text-right">
            <p className="text-[11px] uppercase tracking-wide text-slate-500 font-semibold">Valor do título</p>
            <p className="text-xl font-bold text-slate-900 tabular-nums">{moeda(boleto.valor_total)}</p>
          </div>
        </div>

        <div className="mt-4 ml-6 grid gap-x-6 gap-y-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
          <p className="flex items-center gap-1.5 text-slate-600">
            <CalendarDays className="h-3.5 w-3.5 text-slate-400" />
            Vencimento <span className="font-semibold text-slate-800">{data(boleto.vencimento)}</span>
          </p>
          <p className="flex items-center gap-1.5 text-slate-600">
            <Smartphone className="h-3.5 w-3.5 text-slate-400" />
            <span className="font-semibold text-slate-800">{boleto.qtd_linhas}</span> linhas
          </p>
          <p className="flex items-center gap-1.5 text-slate-600">
            <Building2 className="h-3.5 w-3.5 text-slate-400" />
            NFCOM <span className="font-semibold text-slate-800">{boleto.nfcom_numero || '—'}</span>
            {boleto.nfcom_serie && <span className="text-slate-400">série {boleto.nfcom_serie}</span>}
          </p>
          <p className="flex items-center gap-1.5 text-slate-600">
            <CalendarDays className="h-3.5 w-3.5 text-slate-400" />
            Competência <span className="font-semibold text-slate-800">{boleto.competencia || '—'}</span>
          </p>
        </div>
      </button>

      {aberto && (
        <div className="p-3 border-t border-slate-100 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="px-4 py-2 font-semibold">Linha</th>
                <th className="px-4 py-2 font-semibold">Responsável</th>
                <th className="px-4 py-2 font-semibold">Centro de custo</th>
                {detalharExcedente && (
                  <>
                    <th className="px-4 py-2 font-semibold text-right">Mensalidade</th>
                    <th className="px-4 py-2 font-semibold text-right">Excedente</th>
                  </>
                )}
                <th className="px-4 py-2 font-semibold text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {boleto.linhas.map((linha) => (
                <LinhaDetalhe
                  key={linha.numero}
                  linha={linha}
                  nomeCentro={nomeCentro}
                  detalharExcedente={detalharExcedente}
                />
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-slate-200">
                <td className={`px-4 py-2 text-slate-900 ${temAjustes ? 'font-semibold' : 'font-bold'}`} colSpan={2}>
                  {temAjustes ? 'Soma das linhas' : 'Total'} · {boleto.qtd_linhas} linha(s)
                </td>
                <td />
                {detalharExcedente && (
                  <>
                    <td className="px-4 py-2 text-right tabular-nums text-slate-600">
                      {moeda(somar(boleto.linhas.map((l) => l.valor_mensalidades)))}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-amber-700">
                      {moeda(somar(boleto.linhas.map((l) => l.valor_uso)))}
                    </td>
                  </>
                )}
                <td className={`px-4 py-2 text-right tabular-nums text-slate-900 ${temAjustes ? 'font-semibold' : 'font-bold'}`}>
                  {moeda(somar(boleto.linhas.map((l) => l.valor)))}
                </td>
              </tr>
              {/* Lançamentos da conta: não pertencem a linha nenhuma, então a
                  soma das linhas sozinha não daria o valor do boleto. Explicitar
                  cada um evita que a diferença pareça erro de leitura. */}
              {boleto.ajustes.map((ajuste, i) => (
                <tr key={i}>
                  <td className="px-4 py-1.5 text-slate-600" colSpan={colunas - 1}>
                    {ajuste.descricao}
                    <span className="ml-2 text-[11px] text-slate-400">rateado entre os centros de custo</span>
                  </td>
                  <td className="px-4 py-1.5 text-right tabular-nums font-medium text-slate-700">
                    {moeda(ajuste.valor)}
                  </td>
                </tr>
              ))}
              {temAjustes && (
                <tr className="border-t border-slate-200">
                  <td className="px-4 py-2 font-bold text-slate-900" colSpan={colunas - 1}>
                    Total do título
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums font-bold text-slate-900">
                    {moeda(boleto.valor_total)}
                  </td>
                </tr>
              )}
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}

/** Rascunho de cadastro de uma linha pendente, editado dentro do modal. */
interface Rascunho {
  centro_custo: string;
  classe_valor: string;
  colaborador_nome: string;
}

/**
 * Alerta bloqueante das linhas sem destino contábil — resolvido ali mesmo.
 * Salva em lote e reprocessa, para o usuário não precisar sair do fluxo.
 *
 * Cobre dois casos: linha fora do cadastro (tudo em branco) e linha cadastrada
 * a que falta centro de custo ou classe de valor — nesse caso os campos já vêm
 * preenchidos com o que existe e só o que falta fica vazio.
 */
function ModalPendencias({ pendencias, onFechar, onResolvido, addToast }: {
  pendencias: api.PendenciaClaro[];
  onFechar: () => void;
  onResolvido: () => Promise<void>;
  addToast: (m: string, t: Toast['type']) => void;
}) {
  const [rascunhos, setRascunhos] = useState<Record<string, Rascunho>>(() =>
    Object.fromEntries(
      pendencias.map((p) => [
        p.numero,
        {
          centro_custo: p.centro_custo,
          classe_valor: p.classe_valor,
          colaborador_nome: p.colaborador_nome,
        },
      ]),
    ),
  );
  const [salvando, setSalvando] = useState(false);

  // O ERP recusa sem centro de custo OU sem classe: os dois são obrigatórios.
  const preenchidas = pendencias.filter(
    (p) => rascunhos[p.numero]?.centro_custo.trim() && rascunhos[p.numero]?.classe_valor.trim(),
  );
  const editar = (numero: string, campo: keyof Rascunho, valor: string) =>
    setRascunhos((atual) => ({ ...atual, [numero]: { ...atual[numero], [campo]: valor } }));

  const salvar = async () => {
    setSalvando(true);
    try {
      await api.salvarLinhasTelefonicasEmLote(
        preenchidas.map((p) => ({
          numero: p.numero,
          centro_custo: rascunhos[p.numero].centro_custo.trim(),
          classe_valor: rascunhos[p.numero].classe_valor.trim(),
          // A conta vem do próprio boleto que acabou de cobrar a linha. Se ela
          // apareceu em mais de uma conta, fica vazia — não dá para adivinhar.
          conta: p.contas.length === 1 ? p.contas[0] : '',
          colaborador_cpf: '',
          colaborador_nome: rascunhos[p.numero].colaborador_nome.trim(),
          ativo: true,
          observacao: '',
        })),
      );
      addToast(`${preenchidas.length} linha(s) cadastrada(s). Reprocessando…`, 'success');
      await onResolvido();
      onFechar();
    } catch (erro) {
      addToast(erro instanceof ApiError ? erro.message : 'Falha ao cadastrar as linhas.', 'error');
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-3xl max-h-[85vh] flex flex-col">
        <div className="p-5 border-b border-slate-100 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              Linhas sem destino contábil
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              Estas linhas foram cobradas mas ainda não têm destino contábil completo. Centro de custo
              e classe de valor são obrigatórios. O ERP recusa o lançamento sem eles. O que já existe
              no cadastro vem preenchido, e a conta Claro sai do próprio boleto.
            </p>
          </div>
          <button onClick={onFechar} className="text-slate-400 hover:text-slate-600 shrink-0">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="overflow-y-auto p-3">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="px-3 py-2 font-semibold">Linha</th>
                <th className="px-3 py-2 font-semibold text-right">Valor</th>
                <th className="px-3 py-2 font-semibold">Centro de custo *</th>
                <th className="px-3 py-2 font-semibold">Classe de valor *</th>
                <th className="px-3 py-2 font-semibold">Responsável</th>
              </tr>
            </thead>
            <tbody>
              {pendencias.map((p) => (
                <tr key={p.numero} className="border-t border-slate-100">
                  <td className="px-3 py-2 font-medium text-slate-800 whitespace-nowrap">
                    {p.numero_exibicao}
                    {!p.bloqueia && (
                      <span
                        className="ml-2 text-[10px] font-semibold text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded-full"
                        title="Sem valor cobrado neste boleto. Não impede o lançamento."
                      >
                        não trava
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-600">{moeda(p.valor)}</td>
                  <td className="px-3 py-2">
                    <input
                      value={rascunhos[p.numero]?.centro_custo ?? ''}
                      onChange={(e) => editar(p.numero, 'centro_custo', e.target.value)}
                      placeholder="ex.: 1101"
                      className="w-28 rounded-lg border border-slate-200 px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-slate-900/10"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      value={rascunhos[p.numero]?.classe_valor ?? ''}
                      onChange={(e) => editar(p.numero, 'classe_valor', e.target.value)}
                      className="w-24 rounded-lg border border-slate-200 px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-slate-900/10"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      value={rascunhos[p.numero]?.colaborador_nome ?? ''}
                      onChange={(e) => editar(p.numero, 'colaborador_nome', e.target.value)}
                      placeholder="opcional"
                      className="w-full min-w-[10rem] rounded-lg border border-slate-200 px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-slate-900/10"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="p-4 border-t border-slate-100 flex items-center justify-between gap-3">
          <p className="text-xs text-slate-500">
            {preenchidas.length} de {pendencias.length} preenchida(s)
          </p>
          <div className="flex gap-2">
            <button onClick={onFechar} className="text-xs font-semibold text-slate-600 px-4 py-2 rounded-xl hover:bg-slate-100">
              Cancelar
            </button>
            <button
              onClick={salvar}
              disabled={salvando || preenchidas.length === 0}
              className="text-xs font-semibold text-white bg-slate-900 px-4 py-2 rounded-xl hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-2"
            >
              {salvando ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              Cadastrar e reprocessar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ClaroResultScreen({
  tipo, competence, resposta, onBackToFlow, onConfirmSend, onReprocessar, addToast, somenteLeitura,
  titulosPorConta,
}: Props) {
  const r = comoResultadoClaro(resposta);
  const [baixando, setBaixando] = useState(false);
  // Consolidado por centro de custo: fechado por padrão. É conferência
  // contábil, não a leitura principal da prévia — aberto, empurrava os
  // boletos para fora da tela.
  const [ccAberto, setCcAberto] = useState(false);
  // Destinos (centro de custo + classe) expandidos para mostrar as linhas.
  const [destinosAbertos, setDestinosAbertos] = useState<Set<string>>(new Set());
  const [modalAberto, setModalAberto] = useState(false);

  // Nome amigável do centro de custo, do mesmo cadastro usado nas Configurações.
  // Falha silenciosa: sem o dicionário a prévia continua válida, só mostra o código.
  const [centros, setCentros] = useState<api.CentroCusto[]>([]);
  useEffect(() => {
    api.listarCentrosCusto().then(setCentros).catch(() => setCentros([]));
  }, []);
  const nomePorCodigo = useMemo(() => new Map(centros.map((c) => [c.codigo, c.nome])), [centros]);

  // Linhas de cada destino contábil (centro de custo + classe), reunidas de
  // TODOS os boletos — é a mesma composição que virou item do título. Sai do
  // snapshot, então funciona igual na prévia e na consulta do histórico.
  const linhasPorDestino = useMemo(() => {
    const mapa = new Map<string, Array<{ conta: string; linha: LinhaClaro }>>();
    for (const boleto of r.boletos) {
      for (const linha of boleto.linhas) {
        if (!linha.completa) continue;
        const chave = destinoChave(linha.centro_custo, linha.classe_valor);
        if (!mapa.has(chave)) mapa.set(chave, []);
        mapa.get(chave)!.push({ conta: boleto.conta || boleto.arquivo, linha });
      }
    }
    for (const lista of mapa.values()) lista.sort((a, b) => Number(b.linha.valor) - Number(a.linha.valor));
    return mapa;
  }, [r.boletos]);

  const alternarDestino = (chave: string) =>
    setDestinosAbertos((atual) => {
      const proximo = new Set(atual);
      if (proximo.has(chave)) proximo.delete(chave);
      else proximo.add(chave);
      return proximo;
    });

  const competencia = useMemo(
    () => competence || r.boletos[0]?.competencia || '',
    [competence, r.boletos],
  );

  const baixarCsv = async () => {
    setBaixando(true);
    try {
      await api.baixarCsv(tipo);
    } catch (erro) {
      addToast(erro instanceof ApiError ? erro.message : 'Falha ao baixar o CSV.', 'error');
    } finally {
      setBaixando(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {!somenteLeitura && (
            <button onClick={onBackToFlow} className="text-slate-400 hover:text-slate-700">
              <ArrowLeft className="h-5 w-5" />
            </button>
          )}
          <div>
            <h1 className="text-lg font-bold text-slate-900">Telefonia Claro: prévia do lançamento</h1>
            <p className="text-xs text-slate-500">
              Competência {competencia || '—'} · {r.totais.qtd_boletos} boleto(s) ={' '}
              {r.totais.qtd_boletos} Autorização(ões) de Entrega
            </p>
          </div>
        </div>
        {!somenteLeitura && (
          <div className="flex gap-2">
            <button
              onClick={baixarCsv}
              disabled={baixando}
              className="text-xs font-semibold text-slate-700 bg-white border border-slate-200 px-4 py-2 rounded-xl hover:bg-slate-50 inline-flex items-center gap-2"
            >
              {baixando ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileDown className="h-3.5 w-3.5" />}
              Exportar CSV
            </button>
          </div>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Cartao icone={FileText} rotulo="Títulos a lançar" valor={String(r.totais.qtd_boletos)} />
        <Cartao icone={Banknote} rotulo="Valor total" valor={moeda(r.totais.valor_total)} />
        <Cartao icone={Smartphone} rotulo="Linhas cobradas" valor={String(r.totais.qtd_linhas)} />
        <Cartao
          icone={AlertTriangle}
          rotulo="Cadastro pendente"
          valor={r.totais.qtd_incompletas === 0 ? 'nenhuma' : `${r.totais.qtd_incompletas} linha(s)`}
          destaque={r.totais.qtd_incompletas === 0 ? 'ok' : 'alerta'}
        />
      </div>

      {r.bloqueado && (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-bold text-amber-900">Lançamento bloqueado</p>
              <ul className="text-xs text-amber-800 mt-1 space-y-0.5">
                {r.bloqueios.map((motivo, i) => (
                  <li key={i}>• {motivo}</li>
                ))}
              </ul>
            </div>
          </div>
          {!somenteLeitura && r.pendencias.length > 0 && (
            <button
              onClick={() => setModalAberto(true)}
              className="text-xs font-semibold text-white bg-amber-600 px-4 py-2 rounded-xl hover:bg-amber-700 shrink-0"
            >
              Cadastrar linhas
            </button>
          )}
        </div>
      )}

      {resposta.alertas_validacao.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-4 space-y-1.5">
          {resposta.alertas_validacao.map((alerta, i) => (
            <p key={i} className="text-xs text-slate-600 flex items-start gap-2">
              <AlertTriangle className="h-3.5 w-3.5 text-amber-500 shrink-0 mt-0.5" />
              {alerta}
            </p>
          ))}
        </div>
      )}

      {r.por_centro_custo.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
          <button
            onClick={() => setCcAberto((v) => !v)}
            className="w-full p-4 px-5 flex items-center gap-3 text-left hover:bg-slate-50/60 transition-colors cursor-pointer"
          >
            <ChevronRight className={`h-4 w-4 text-slate-400 shrink-0 transition-transform ${ccAberto ? 'rotate-90' : ''}`} />
            <div className="min-w-0">
              <h3 className="text-sm font-bold text-slate-900">Consolidado por centro de custo</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Soma de todos os boletos desta execução, por centro de custo e classe de valor.
              </p>
            </div>
            {/* Fechado, o cabeçalho ainda responde o essencial: quantos destinos
                contábeis e quanto foi rateado. */}
            <div className="ml-auto text-right shrink-0">
              <p className="text-xs font-semibold text-slate-900 tabular-nums">
                {moeda(somar(r.por_centro_custo.map((g) => g.valor)))}
              </p>
              <p className="text-[11px] text-slate-500">
                {r.por_centro_custo.length} destino(s) contábil(is)
              </p>
            </div>
          </button>
          <div className={`overflow-x-auto border-t border-slate-100 ${ccAberto ? '' : 'hidden'}`}>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-500">
                  <th className="px-5 py-2 font-semibold">Centro de custo</th>
                  <th className="px-5 py-2 font-semibold">Classe de valor</th>
                  <th className="px-5 py-2 font-semibold text-right">Linhas</th>
                  <th className="px-5 py-2 font-semibold text-right">Valor</th>
                </tr>
              </thead>
              <tbody>
                {r.por_centro_custo.map((grupo) => (
                  /* Chave = centro de custo + classe: o mesmo CC aparece uma vez
                     por classe de valor, como nos itens do título. */
                  <tr key={`${grupo.centro_custo}|${grupo.classe_valor ?? ''}`} className="border-t border-slate-100">
                    <td className="px-5 py-2">
                      <span className="font-medium text-slate-800">{grupo.centro_custo}</span>
                      {nomePorCodigo.get(grupo.centro_custo) && (
                        <span className="ml-2 text-slate-500">{nomePorCodigo.get(grupo.centro_custo)}</span>
                      )}
                    </td>
                    <td className="px-5 py-2 tabular-nums text-slate-600">{grupo.classe_valor || '—'}</td>
                    <td className="px-5 py-2 text-right tabular-nums text-slate-600">{grupo.qtd_linhas}</td>
                    <td className="px-5 py-2 text-right tabular-nums font-semibold text-slate-900">{moeda(grupo.valor)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-slate-200">
                  <td className="px-5 py-2 font-bold text-slate-900" colSpan={2}>Total rateado</td>
                  <td className="px-5 py-2 text-right tabular-nums text-slate-600">
                    {somar(r.por_centro_custo.map((g) => g.qtd_linhas))}
                  </td>
                  <td className="px-5 py-2 text-right tabular-nums font-bold text-slate-900">
                    {moeda(somar(r.por_centro_custo.map((g) => g.valor)))}
                  </td>
                </tr>
                {/* Só aparece quando falta cadastro: deixa explícito por que o
                    rateado não bate com o total dos boletos. */}
                {Number(r.totais.valor_incompleto) > 0 && (
                  <tr className="border-t border-slate-100">
                    <td className="px-5 py-2 text-amber-800" colSpan={3}>
                      Ainda sem centro de custo
                    </td>
                    <td className="px-5 py-2 text-right tabular-nums font-semibold text-amber-800">
                      {moeda(r.totais.valor_incompleto)}
                    </td>
                  </tr>
                )}
              </tfoot>
            </table>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {r.boletos.map((boleto) => (
          <CartaoBoleto
            key={boleto.arquivo}
            boleto={boleto}
            nomeCentro={(codigo) => nomePorCodigo.get(codigo) ?? ''}
            titulo={titulosPorConta?.[boleto.conta]}
          />
        ))}
      </div>

      {modalAberto && (
        <ModalPendencias
          pendencias={r.pendencias}
          onFechar={() => setModalAberto(false)}
          onResolvido={onReprocessar}
          addToast={addToast}
        />
      )}

      {/* Confirmação FLUTUANTE (padrão das outras telas de resultado). Um título
          por boleto: com linha cobrada sem cadastro o lançamento fica bloqueado,
          então o botão só habilita quando não há bloqueio. */}
      {!somenteLeitura && createPortal(
        <div className="fixed bottom-6 right-6 z-40">
          <button
            onClick={() => onConfirmSend()}
            disabled={r.bloqueado || r.boletos.length === 0}
            title={
              r.bloqueado
                ? 'Resolva as pendências de cadastro antes de lançar: há linha cobrada sem centro de custo ou classe de valor.'
                : 'Registra a execução no histórico e gera uma Autorização de Entrega por boleto no ERP.'
            }
            className="flex items-center gap-2 py-3 px-6 bg-emerald-600 hover:bg-emerald-700 text-white rounded-2xl text-xs font-bold shadow-xl shadow-emerald-950/20 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Confirmar e lançar {r.boletos.length === 1 ? 'boleto' : `${r.boletos.length} boletos`}
          </button>
        </div>,
        document.body,
      )}
    </div>
  );
}
