import { Fragment, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  FileDown,
  FileText,
  Users,
  Banknote,
  AlertTriangle,
  ChevronRight,
  ChevronDown,
  Info,
  ShieldAlert,
  Briefcase,
  MoreVertical,
  Search,
  Loader2,
} from 'lucide-react';
import * as api from '../api';
import { moeda } from '../formatacao';
import Secao from './resultado/Secao';
import ModalAuditoria from './coparticipacao/ModalAuditoria';
import ModalCompetenciaTxt from './coparticipacao/ModalCompetenciaTxt';
import ModalConfirmarPj from './coparticipacao/ModalConfirmarPj';
import TabelaOcorrencias from './coparticipacao/TabelaOcorrencias';
import { rotuloOperadora } from './coparticipacao/rotulos';
import { ApiError, RespostaProcessamento, ItemCopartResultado, comoResultadoCopart } from '../api';
import { Toast } from '../types';
import CpfCell from './CpfCell';
import Dropdown from './Dropdown';

// Salário e Teto NÃO são exibidos aqui — só na auditoria (ModalAuditoria).
const COLS: Array<{ key: keyof ItemCopartResultado; label: string; num?: boolean }> = [
  { key: 'empresa', label: 'Empresa' },
  { key: 'nome', label: 'Colaborador' },
  { key: 'cpf', label: 'CPF' },
  // Uma linha por colaborador × OPERADORA: quem tem os dois planos aparece duas
  // vezes (um lançamento por plano). Sem esta coluna as duas linhas ficam
  // visualmente idênticas e parecem registro duplicado.
  { key: 'operadora', label: 'Operadora' },
  { key: 'faixa', label: 'Faixa' },
  { key: 'num_eventos', label: 'Eventos', num: true },
  { key: 'valor_bruto', label: 'Bruto', num: true },
  { key: 'valor_descontado', label: 'A Descontar', num: true },
];
const NUM_COLS = new Set<string>(['num_eventos', 'valor_bruto', 'valor_descontado']);

/** Chave única da linha: o CPF sozinho repete quando o colaborador tem dois
 *  planos, e chave repetida faz o React embaralhar/duplicar linhas ao reordenar. */
function chaveItem(it: ItemCopartResultado): string {
  return `${it.cpf}-${(it.operadora || '').toLowerCase()}`;
}

// Empresas com export TXT por empresa (rótulo exibido = valor filtrado no backend).
const EMPRESAS_TXT: Array<{ label: string; valor: string }> = [
  { label: 'Vertex', valor: 'Vertex' },
  { label: 'Zenith', valor: 'Zenith' },
];

interface Props {
  tipo: string;
  competence: string;
  resposta: RespostaProcessamento;
  onBackToFlow: () => void;
  onConfirmSend: () => void;
  onReprocessar: () => Promise<void>;
  addToast: (message: string, type: Toast['type']) => void;
  // Modo leitura (consulta no histórico): esconde as ações que alteram estado
  // (refazer, confirmar, PJ) — as exportações continuam disponíveis.
  somenteLeitura?: boolean;
  /** Execução consultada no histórico: as exportações passam a ler o snapshot
   *  dela, em vez do último processamento em memória (que seria outro rateio). */
  execucaoId?: number;
}

/** Plural sem "(es)": "1 colaborador" / "17 colaboradores". */
function plural(n: number, singular: string, plural: string): string {
  return n === 1 ? singular : plural;
}

const ROTULO_DIVERGENCIA: Record<string, string> = {
  titular_nao_encontrado: 'Titular não encontrado',
  colaborador_desligado: 'Colaborador desligado',
  sem_salario: 'Registro sem salário',
  sem_faixa: 'Salário sem faixa',
  procedimento_nao_classificado: 'Procedimento não classificado',
};
// Divergências que podem ser reclassificadas como PJ.
const ELEGIVEL_PJ = new Set(['titular_nao_encontrado', 'colaborador_desligado']);

export default function CoparticipacaoResultScreen({
  tipo,
  competence,
  resposta,
  onBackToFlow,
  onConfirmSend,
  onReprocessar,
  addToast,
  somenteLeitura,
  execucaoId,
}: Props) {
  // Só admin_area/admin audita (vê salário/teto). Operador não vê a opção "Auditar".
  const podeAuditar = !!resposta.pode_auditar;
  const [baixando, setBaixando] = useState(false);
  const [baixandoTxt, setBaixandoTxt] = useState(false);
  const [baixandoPj, setBaixandoPj] = useState(false);
  // Empresa escolhida para o export TXT; não nula = modal de competência aberto
  // (a coparticipação não armazena competência, então ela é pedida no modal).
  const [exportEmpresa, setExportEmpresa] = useState<string | null>(null);
  const { total_itens, alertas_validacao } = resposta;
  const r = comoResultadoCopart(resposta);
  // PJ não entram no TXT do ERP (a API não os retorna — sem filial/matrícula).
  const qtdPj = r.itens.filter((i) => i.pj).length;
  // Fora do lançamento automático: PJ (cobrado na nota) e teto atingido (tratativa
  // manual). Contados por PESSOA — quem tem os dois planos gera dois itens.
  const cpfsNoTeto = new Set(r.itens.filter((i) => i.teto_aplicado && !i.pj).map((i) => i.cpf));
  // Bloqueado por outro motivo (registro ativo equivalente em mais de uma
  // empresa/matrícula — transferência sem baixa na origem).
  const cpfsCadastroAmbiguo = new Set(
    r.itens.filter((i) => i.bloqueado_envio && !i.pj && !i.teto_aplicado).map((i) => i.cpf),
  );
  const cpfsForaDoErp = new Set(
    r.itens.filter((i) => i.bloqueado_envio ?? (i.pj || i.teto_aplicado)).map((i) => i.cpf),
  );
  // Pessoas (não itens): dois planos = um colaborador, dois lançamentos.
  const qtdColaboradores = new Set(r.itens.map((i) => i.cpf)).size;
  const enviaveis = r.itens.filter((i) => !(i.bloqueado_envio ?? (i.pj || i.teto_aplicado)));
  const totalAoErp = enviaveis.reduce((soma, i) => soma + Number(i.valor_descontado || 0), 0);

  const [ordCol, setOrdCol] = useState<keyof ItemCopartResultado>('nome');
  const [ordDir, setOrdDir] = useState<'asc' | 'desc'>('asc');
  const [menuAberto, setMenuAberto] = useState<string | null>(null);
  // Linhas com as ocorrências abertas (chave = cpf-operadora, igual à da linha).
  const [ocorrenciasAbertas, setOcorrenciasAbertas] = useState<Set<string>>(new Set());
  const toggleOcorrencias = (chave: string) =>
    setOcorrenciasAbertas((s) => {
      const n = new Set(s);
      if (n.has(chave)) n.delete(chave);
      else n.add(chave);
      return n;
    });
  const [auditando, setAuditando] = useState<ItemCopartResultado | null>(null);
  const [movendo, setMovendo] = useState<string | null>(null);
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [modoSelecao, setModoSelecao] = useState(false);
  const [confirmandoPJ, setConfirmandoPJ] = useState<{ cpf: string; nome: string } | null>(null);
  // Filtros do card "Desconto por Colaborador".
  const [busca, setBusca] = useState('');
  const [filtroEmpresa, setFiltroEmpresa] = useState(''); // '' = todas
  const [filtroPj, setFiltroPj] = useState<'todos' | 'pj' | 'clt'>('todos');
  const [soTeto, setSoTeto] = useState(false);
  // Empresas presentes (exclui "PJ", que é marcador do colaborador, não empresa).
  const empresasPresentes = [
    ...new Set(r.itens.map((i) => i.empresa).filter((e) => e && e.toUpperCase() !== 'PJ')),
  ].sort();

  const toggleSel = (cpf: string) =>
    setSelecionados((s) => {
      const n = new Set(s);
      if (n.has(cpf)) n.delete(cpf);
      else n.add(cpf);
      return n;
    });

  const moverCpfParaPJ = async (cpf: string, nome: string) => {
    setMovendo(cpf);
    try {
      await api.adicionarPJ(cpf, nome);
      addToast(`${nome} classificado como PJ. Recalculando…`, 'success');
      await onReprocessar();
      addToast('Processamento concluído.', 'success');
    } catch (err) {
      addToast(
        err instanceof ApiError ? err.message : 'Falha ao classificar o colaborador como PJ.',
        'error',
      );
    } finally {
      setMovendo(null);
    }
  };

  const removerDePJ = async (it: ItemCopartResultado) => {
    setMovendo(it.cpf);
    try {
      await api.removerPJ(it.cpf);
      addToast(`Classificação PJ removida de ${it.nome}. Recalculando…`, 'success');
      await onReprocessar();
      addToast('Processamento concluído.', 'success');
    } catch (err) {
      addToast(
        err instanceof ApiError ? err.message : 'Falha ao remover a classificação PJ.',
        'error',
      );
    } finally {
      setMovendo(null);
    }
  };

  // Início da atribuição de PJ. Fora do modo de seleção, abre o modal perguntando
  // se o usuário quer selecionar mais colaboradores. Já no modo de seleção, apenas marca.
  const iniciarPJ = (cpf: string, nome: string) => {
    if (modoSelecao) {
      setSelecionados((s) => new Set(s).add(cpf));
      return;
    }
    setConfirmandoPJ({ cpf, nome });
  };
  // "Não" -> move só este e processa.
  const processarUm = () => {
    if (!confirmandoPJ) return;
    const { cpf, nome } = confirmandoPJ;
    setConfirmandoPJ(null);
    moverCpfParaPJ(cpf, nome);
  };
  // "Sim" -> entra no modo de seleção (checkboxes) já marcando este.
  const selecionarMais = () => {
    if (!confirmandoPJ) return;
    setSelecionados(new Set([confirmandoPJ.cpf]));
    setModoSelecao(true);
    setConfirmandoPJ(null);
  };
  const cancelarSelecao = () => {
    setModoSelecao(false);
    setSelecionados(new Set());
  };

  // Processa todos os selecionados de uma vez (um único reprocessamento).
  const processarSelecaoPJ = async () => {
    const nomeDe = (cpf: string) =>
      r.itens.find((i) => i.cpf === cpf)?.nome ??
      r.divergencias.find((d) => d.cpf === cpf)?.nome ??
      '';
    const alvos = [...selecionados].map((cpf) => ({ cpf, nome: nomeDe(cpf) }));
    if (alvos.length === 0) {
      addToast('Nenhum colaborador selecionado.', 'info');
      return;
    }
    setMovendo('bulk');
    try {
      await Promise.all(alvos.map((a) => api.adicionarPJ(a.cpf, a.nome)));
      addToast(`${alvos.length} colaborador(es) movido(s) para PJ. Recalculando...`, 'success');
      setSelecionados(new Set());
      setModoSelecao(false);
      await onReprocessar();
      addToast('Processamento concluído.', 'success');
    } catch (err) {
      addToast(
        err instanceof ApiError ? err.message : 'Falha ao classificar o colaborador como PJ.',
        'error',
      );
    } finally {
      setMovendo(null);
    }
  };

  const clicarCol = (key: keyof ItemCopartResultado) => {
    if (ordCol === key) setOrdDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setOrdCol(key);
      setOrdDir('asc');
    }
  };
  const itensFiltrados = r.itens.filter((it) => {
    if (filtroEmpresa && it.empresa !== filtroEmpresa) return false;
    if (filtroPj === 'pj' && !it.pj) return false;
    if (filtroPj === 'clt' && it.pj) return false;
    if (soTeto && !it.teto_aplicado) return false;
    const q = busca.trim().toLowerCase();
    if (q) {
      const qd = q.replace(/\D/g, '');
      const casaTexto =
        it.nome.toLowerCase().includes(q) || (it.matricula || '').toLowerCase().includes(q);
      const casaCpf = !!qd && it.cpf.replace(/\D/g, '').includes(qd);
      if (!casaTexto && !casaCpf) return false;
    }
    return true;
  });
  const itensOrdenados = [...itensFiltrados].sort((a, b) => {
    const m = ordDir === 'asc' ? 1 : -1;
    const comparar = NUM_COLS.has(ordCol as string)
      ? Number(a[ordCol] ?? 0) - Number(b[ordCol] ?? 0)
      : String(a[ordCol] ?? '').localeCompare(String(b[ordCol] ?? ''), 'pt-BR');
    // Desempate por nome + operadora: sem ele, linhas com o mesmo valor na coluna
    // ordenada trocam de lugar entre renderizações (parece ordenação quebrada).
    if (comparar !== 0) return comparar * m;
    return chaveItem(a).localeCompare(chaveItem(b));
  });

  // Lançamentos que o ERP vai receber NA VISÃO ATUAL (respeita os filtros): um por
  // matrícula, já descontando quem não é enviado. É este número que aparece na
  // confirmação do ERP ("N matrícula(s) incluída(s)"), e não o total de linhas.
  const lancamentosAoErp = new Set(
    itensOrdenados
      .filter((i) => !(i.bloqueado_envio ?? (i.pj || i.teto_aplicado)))
      .map((i) => `${i.filial}-${i.matricula}`),
  ).size;

  const todosSelecionados =
    itensOrdenados.length > 0 && itensOrdenados.every((i) => selecionados.has(i.cpf));
  const toggleTodos = () =>
    setSelecionados(todosSelecionados ? new Set() : new Set(itensOrdenados.map((i) => i.cpf)));

  const handleBaixarCsv = async () => {
    setBaixando(true);
    try {
      // No histórico a fonte é o snapshot da execução; no fluxo, o processamento atual.
      await (execucaoId != null ? api.baixarCsvExecucao(execucaoId) : api.baixarCsv(tipo));
      addToast('Arquivo CSV gerado. O download será iniciado.', 'success');
    } catch (err) {
      addToast(err instanceof ApiError ? err.message : 'Falha ao exportar o arquivo CSV.', 'error');
    } finally {
      setBaixando(false);
    }
  };

  // CSV dos PJs: eles não entram no lançamento em folha (sem matrícula/filial no
  // Protheus). O desconto é cobrado na nota — este CSV apoia esse processo manual.
  const handleBaixarPjCsv = async () => {
    setBaixandoPj(true);
    try {
      await (execucaoId != null ? api.baixarPjCsvExecucao(execucaoId) : api.baixarPjCsv(tipo));
      addToast('Relação de colaboradores PJ gerada. O download será iniciado.', 'success');
    } catch (err) {
      addToast(
        err instanceof ApiError ? err.message : 'Falha ao exportar a relação de colaboradores PJ.',
        'error',
      );
    } finally {
      setBaixandoPj(false);
    }
  };

  // Abre o fluxo do TXT para uma empresa: guarda a empresa e abre o modal de
  // competência VAZIO (o usuário deve informar a data de referência).
  const iniciarExportTxt = (empresa: string) => {
    setMenuAberto(null);
    setExportEmpresa(empresa);
  };

  const fecharExportTxt = () => {
    setExportEmpresa(null);
  };

  // TXT de redundância p/ importação manual no ERP (competência já em AAAAMM).
  const handleBaixarTxt = async (competencia: string) => {
    if (!competencia || !exportEmpresa) return;
    setBaixandoTxt(true);
    try {
      await api.baixarTxt(tipo, competencia, exportEmpresa);
      addToast('Arquivo TXT gerado. O download será iniciado.', 'success');
      fecharExportTxt();
    } catch (err) {
      addToast(err instanceof ApiError ? err.message : 'Falha ao exportar o arquivo TXT.', 'error');
    } finally {
      setBaixandoTxt(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Coparticipação: desconto em folha</h1>
          {/* Os eventos da coparticipação não carregam competência — o rótulo
              vazio não informa nada, então só aparece quando há valor. */}
          {competence && (
            <p className="text-xs text-slate-500">
              Competência: <strong>{competence}</strong>
            </p>
          )}
        </div>
        {/* Exportar vale também na consulta ao histórico (lendo o snapshot da
            execução); só as ações que alteram estado ficam fora do modo leitura. */}
        <div className="flex gap-2">
          {!somenteLeitura && (
            <button
              onClick={onBackToFlow}
              className="py-2 px-4 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer"
            >
              Refazer importação
            </button>
          )}
          {/* UM botão para todas as exportações: três botões lado a lado ocupavam
              a faixa inteira do cabeçalho e nenhuma delas é ação frequente. */}
          <div className="relative">
            <button
              onClick={() => setMenuAberto((m) => (m === 'export' ? null : 'export'))}
              disabled={total_itens === 0 || baixando || baixandoPj}
              className="flex items-center gap-1.5 py-2 px-4 border border-slate-200 bg-white rounded-xl text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <FileDown className="h-4 w-4 text-slate-500" />
              {baixando || baixandoPj ? 'Gerando…' : 'Exportar'}
              <ChevronDown
                className={`h-3.5 w-3.5 text-slate-400 transition-transform ${menuAberto === 'export' ? 'rotate-180' : ''}`}
              />
            </button>
            {menuAberto === 'export' && (
              <div className="absolute right-0 top-11 z-20 w-72 bg-white border border-slate-200 rounded-xl shadow-lg py-1 text-left">
                <div className="px-3 py-1.5 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                  Planilhas (CSV)
                </div>
                <button
                  onClick={() => {
                    setMenuAberto(null);
                    handleBaixarCsv();
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 cursor-pointer"
                >
                  <FileDown className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                  <span>
                    Relação completa <span className="text-slate-400">({total_itens})</span>
                  </span>
                </button>
                <button
                  onClick={() => {
                    setMenuAberto(null);
                    handleBaixarPjCsv();
                  }}
                  disabled={qtdPj === 0}
                  title="Colaboradores PJ não integram o lançamento em folha: o desconto é cobrado na nota fiscal."
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Briefcase className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                  <span>
                    Colaboradores PJ <span className="text-slate-400">({qtdPj})</span>
                  </span>
                </button>
                {/* O TXT ainda é gerado a partir do último processamento em
                      memória; no histórico ele traria o arquivo de outra execução,
                      então não é oferecido na consulta. */}
                {!somenteLeitura && (
                  <>
                    <div className="mt-1 border-t border-slate-100 px-3 py-1.5 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                      Importação manual no ERP (TXT)
                    </div>
                    {EMPRESAS_TXT.map((e) => (
                      <button
                        key={e.valor}
                        onClick={() => iniciarExportTxt(e.valor)}
                        title="Layout posicional para importar no ERP caso o lançamento via API falhe"
                        className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 cursor-pointer"
                      >
                        <FileText className="h-3.5 w-3.5 text-slate-400 shrink-0" /> {e.label}
                      </button>
                    ))}
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {alertas_validacao.length > 0 && (
        <div className="bg-sky-50 border border-sky-200 rounded-2xl p-4 space-y-1.5">
          {alertas_validacao.map((a, i) => (
            <div key={i} className="flex items-start gap-2 text-xs text-sky-900">
              <Info className="h-4 w-4 text-sky-500 shrink-0 mt-0.5" />
              <span>{a}</span>
            </div>
          ))}
        </div>
      )}

      {/* Tratativa manual: quem NÃO vai ao lançamento automático em folha. Fica
          acima dos KPIs porque muda o que o operador precisa fazer depois. */}
      {cpfsForaDoErp.size > 0 && (
        <div className="bg-white border border-amber-200 rounded-2xl overflow-hidden shadow-sm">
          <div className="flex items-center gap-2.5 bg-amber-50 px-4 py-3 border-b border-amber-200">
            <ShieldAlert className="h-4 w-4 text-amber-500 shrink-0" />
            <h3 className="text-sm font-bold text-amber-900">
              Tratativa manual: {cpfsForaDoErp.size}{' '}
              {plural(cpfsForaDoErp.size, 'colaborador', 'colaboradores')} fora do lançamento em
              folha
            </h3>
          </div>
          {/* Uma linha por motivo: contagem em destaque, rótulo curto e a ação
              esperada. Lista com marcadores e frases longas escondiam o que fazer. */}
          <div className="divide-y divide-slate-100">
            {[
              cpfsNoTeto.size > 0 && {
                chave: 'teto',
                qtd: cpfsNoTeto.size,
                rotulo: 'Teto do percentual atingido',
                acao: 'Não são enviados ao ERP. Trate o desconto manualmente na folha.',
              },
              cpfsCadastroAmbiguo.size > 0 && {
                chave: 'cadastro',
                qtd: cpfsCadastroAmbiguo.size,
                rotulo: 'Registro ativo em mais de uma empresa',
                acao: 'Confirme a transferência no Protheus. Os avisos abaixo mostram os registros em conflito.',
              },
              qtdPj > 0 && {
                chave: 'pj',
                qtd: qtdPj,
                rotulo: 'Classificados como PJ',
                acao: 'Desconto cobrado na nota fiscal. Use "Exportar › Colaboradores PJ".',
              },
            ]
              .filter((m): m is { chave: string; qtd: number; rotulo: string; acao: string } =>
                Boolean(m),
              )
              .map((m) => (
                <div key={m.chave} className="flex items-start gap-3 px-4 py-2.5">
                  <span className="shrink-0 min-w-7 text-center text-xs font-bold text-amber-900 bg-amber-50 border border-amber-200 rounded-lg px-1.5 py-0.5">
                    {m.qtd}
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-slate-800">{m.rotulo}</p>
                    <p className="text-[11px] text-slate-500 leading-relaxed">{m.acao}</p>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-sm flex items-center gap-4">
          <div className="h-12 w-12 bg-brand-50 border border-brand-100 rounded-xl flex items-center justify-center shrink-0">
            <Users className="h-6 w-6 text-brand-900" />
          </div>
          <div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
              Colaboradores
            </span>
            <span className="text-2xl font-bold text-slate-900">{qtdColaboradores}</span>
            {total_itens !== qtdColaboradores && (
              <span className="block text-[10px] text-slate-400">
                {total_itens} lançamentos (quem tem dois planos gera um por plano)
              </span>
            )}
          </div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-sm flex items-center gap-4">
          <div className="h-12 w-12 bg-brand-950 rounded-xl flex items-center justify-center shrink-0 shadow-sm">
            <Banknote className="h-6 w-6 text-brand-300" />
          </div>
          <div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
              Total a Descontar
            </span>
            <span className="text-2xl font-black text-brand-950 font-mono">
              {moeda(r.total_descontado)}
            </span>
            {cpfsForaDoErp.size > 0 && (
              <span className="block text-[10px] text-slate-400">
                {moeda(totalAoErp)} a enviar ao ERP; o restante requer tratativa manual
              </span>
            )}
          </div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-sm flex items-center gap-4">
          <div className="h-12 w-12 bg-amber-50 border border-amber-100 rounded-xl flex items-center justify-center shrink-0">
            <AlertTriangle className="h-6 w-6 text-amber-500" />
          </div>
          <div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
              Divergências / Avisos
            </span>
            <span className="text-2xl font-bold text-slate-900">
              {r.divergencias.length}{' '}
              <span className="text-base text-slate-400">/ {r.avisos.length}</span>
            </span>
          </div>
        </div>
      </div>

      {/* Detalhe por colaborador — card colapsado, ordenável; ações no menu (⋮) */}
      <Secao titulo="Desconto por Colaborador" contador={total_itens}>
        <div className="p-4 px-5 border-b border-slate-100 flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
            <input
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar por nome, CPF ou matrícula…"
              className="w-full pl-8 pr-3 py-2 border border-slate-200 rounded-xl text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-200"
            />
          </div>
          {empresasPresentes.length > 1 && (
            <Dropdown
              value={filtroEmpresa}
              onChange={setFiltroEmpresa}
              larguraMenu="w-48"
              opcoes={[
                { value: '', label: 'Todas as empresas' },
                ...empresasPresentes.map((e) => ({ value: e, label: e })),
              ]}
            />
          )}
          <Dropdown
            value={filtroPj}
            onChange={(v) => setFiltroPj(v as 'todos' | 'pj' | 'clt')}
            larguraMenu="w-32"
            opcoes={[
              { value: 'todos', label: 'Todos' },
              { value: 'pj', label: 'PJ' },
              { value: 'clt', label: 'CLT' },
            ]}
          />
          <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer select-none px-1">
            <input
              type="checkbox"
              checked={soTeto}
              onChange={(e) => setSoTeto(e.target.checked)}
              className="cursor-pointer"
            />
            Atingiram o teto
          </label>
          {(busca || filtroEmpresa || filtroPj !== 'todos' || soTeto) && (
            <button
              onClick={() => {
                setBusca('');
                setFiltroEmpresa('');
                setFiltroPj('todos');
                setSoTeto(false);
              }}
              className="text-[11px] font-semibold text-slate-500 hover:text-slate-700 cursor-pointer px-2"
            >
              Limpar
            </button>
          )}
          {/* Duas contagens diferentes, e a confusão entre elas é real: a tabela
              lista LINHAS (colaborador × operadora) e o ERP recebe LANÇAMENTOS
              (um por matrícula, com os planos somados). Quem tem dois planos
              aparece em duas linhas e vira um lançamento só. */}
          <span className="text-[11px] text-slate-400 ml-auto whitespace-nowrap">
            exibindo {itensOrdenados.length} de {r.itens.length}
            {' · '}
            <span title="Um lançamento por matrícula: colaborador com dois planos entra somado, num único registro no ERP. Exclui PJ e bloqueados.">
              {lancamentosAoErp} lançamento(s) ao ERP
            </span>
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="bg-slate-50 text-slate-400 font-bold border-b border-slate-100 text-[10px] uppercase tracking-wider">
                {modoSelecao && (
                  <th className="py-3 pl-4 w-8">
                    <input
                      type="checkbox"
                      checked={todosSelecionados}
                      onChange={toggleTodos}
                      className="cursor-pointer"
                      title="Selecionar todos"
                    />
                  </th>
                )}
                {COLS.map((c) => (
                  <th
                    key={c.key}
                    onClick={() => clicarCol(c.key)}
                    className={`py-3 px-3 cursor-pointer select-none hover:text-slate-600 ${c.num ? 'text-right' : ''}`}
                  >
                    {c.label}
                    {ordCol === c.key ? (ordDir === 'asc' ? ' ▲' : ' ▼') : ''}
                  </th>
                ))}
                <th className="py-3 px-3 w-10"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {itensOrdenados.map((it) => {
                const chave = chaveItem(it);
                const aberto = ocorrenciasAbertas.has(chave);
                return (
                  <Fragment key={chave}>
                    <tr
                      className={`hover:bg-slate-50/60 font-medium ${modoSelecao && selecionados.has(it.cpf) ? 'bg-brand-50/40' : ''}`}
                    >
                      {modoSelecao && (
                        <td className="py-3 pl-4">
                          <input
                            type="checkbox"
                            checked={selecionados.has(it.cpf)}
                            onChange={() => toggleSel(it.cpf)}
                            className="cursor-pointer"
                          />
                        </td>
                      )}
                      <td className="py-3 px-3">{it.empresa}</td>
                      {/* Clicar no nome abre as ocorrências do colaborador, como o
                      detalhamento de vidas/dependentes na mensalidade. */}
                      <td className="py-3 px-3 font-semibold text-slate-900">
                        <button
                          onClick={() => toggleOcorrencias(chave)}
                          title="Ver ocorrências do colaborador"
                          className="inline-flex items-center gap-1 text-left hover:text-brand-900 cursor-pointer"
                        >
                          <ChevronRight
                            className={`h-3 w-3 text-slate-400 transition-transform shrink-0 ${aberto ? 'rotate-90' : ''}`}
                          />
                          <span>{it.nome}</span>
                        </button>
                        {it.pj && (
                          <span className="ml-1.5 inline-flex items-center gap-0.5 text-[9px] font-bold text-brand-800 bg-brand-50 border border-brand-100 px-1 py-0.5 rounded align-middle">
                            <Briefcase className="h-2.5 w-2.5" />
                            PJ
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-3">
                        <CpfCell cpf={it.cpf} />
                      </td>
                      <td className="py-3 px-3">{rotuloOperadora(it.operadora)}</td>
                      <td className="py-3 px-3">{it.faixa}</td>
                      <td className="py-3 px-3 text-right">{it.num_eventos}</td>
                      <td className="py-3 px-3 text-right font-mono text-slate-500">
                        {moeda(it.valor_bruto)}
                      </td>
                      <td className="py-3 px-3 text-right font-mono font-bold text-brand-950">
                        {moeda(it.valor_descontado)}
                        {/* Qualquer bloqueio aparece na linha (teto, cadastro ambíguo);
                        PJ já tem marca própria ao lado do nome. */}
                        {(it.bloqueado_envio ?? it.teto_aplicado) && !it.pj && (
                          <span
                            title={
                              it.motivo_bloqueio || 'Não enviado ao ERP; requer tratativa manual.'
                            }
                            className="ml-1.5 text-[9px] font-bold text-amber-600 bg-amber-50 border border-amber-200 px-1 py-0.5 rounded align-middle"
                          >
                            {it.teto_aplicado ? 'Teto (não enviado)' : 'Não enviado'}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-3 text-right relative">
                        {(podeAuditar || !somenteLeitura) && (
                          <button
                            onClick={() =>
                              setMenuAberto((m) => (m === chaveItem(it) ? null : chaveItem(it)))
                            }
                            className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-700 cursor-pointer"
                            title="Ações"
                          >
                            <MoreVertical className="h-4 w-4" />
                          </button>
                        )}
                        {/* Por linha (CPF+operadora): com o CPF sozinho, o clique numa
                        linha abria o menu das duas linhas do mesmo colaborador. */}
                        {menuAberto === chaveItem(it) && (
                          <div className="absolute right-3 top-9 z-20 w-48 bg-white border border-slate-200 rounded-xl shadow-lg py-1 text-left">
                            {podeAuditar && (
                              <button
                                onClick={() => {
                                  setMenuAberto(null);
                                  setAuditando(it);
                                }}
                                className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 cursor-pointer"
                              >
                                <Search className="h-3.5 w-3.5 text-slate-400" /> Auditar cálculo
                              </button>
                            )}
                            {!somenteLeitura &&
                              (it.pj ? (
                                <button
                                  onClick={() => {
                                    setMenuAberto(null);
                                    removerDePJ(it);
                                  }}
                                  disabled={movendo === it.cpf}
                                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 cursor-pointer disabled:opacity-50"
                                >
                                  <Briefcase className="h-3.5 w-3.5 text-slate-400" /> Remover
                                  classificação PJ
                                </button>
                              ) : (
                                <button
                                  onClick={() => {
                                    setMenuAberto(null);
                                    iniciarPJ(it.cpf, it.nome);
                                  }}
                                  disabled={movendo === it.cpf}
                                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 cursor-pointer disabled:opacity-50"
                                >
                                  <Briefcase className="h-3.5 w-3.5 text-slate-400" /> Mover para PJ
                                </button>
                              ))}
                          </div>
                        )}
                      </td>
                    </tr>
                    {aberto && (
                      <tr className="bg-slate-50/40">
                        <td colSpan={COLS.length + (modoSelecao ? 2 : 1)} className="px-3 pb-3">
                          <div className="pl-6">
                            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1">
                              Ocorrências · {rotuloOperadora(it.operadora)} ({it.ocorrencias.length}
                              )
                            </div>
                            <TabelaOcorrencias ocorrencias={it.ocorrencias} />
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
              {itensOrdenados.length === 0 && (
                <tr>
                  <td
                    colSpan={COLS.length + (modoSelecao ? 2 : 1)}
                    className="py-8 text-center text-slate-400"
                  >
                    {r.itens.length === 0
                      ? 'Nenhum colaborador com desconto (verifique as divergências).'
                      : 'Nenhum colaborador para os filtros aplicados.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="bg-slate-50 p-4 px-5 border-t border-slate-100 text-right">
          <span className="text-xs font-semibold text-slate-500 mr-2">Total a descontar:</span>
          <span className="text-sm font-black text-brand-950 font-mono">
            {moeda(r.total_descontado)}
          </span>
        </div>
      </Secao>

      {/* Fecha o menu ao clicar fora */}
      {menuAberto && <div className="fixed inset-0 z-10" onClick={() => setMenuAberto(null)} />}

      {/* Overlay de reprocessamento (mover/remover PJ) */}
      {movendo &&
        createPortal(
          <div className="fixed inset-0 z-40 bg-slate-900/30 flex items-center justify-center">
            <div className="bg-white rounded-2xl shadow-xl px-6 py-4 flex items-center gap-3">
              <Loader2 className="h-5 w-5 animate-spin text-brand-900" />
              <span className="text-sm font-semibold text-slate-700">Reprocessando…</span>
            </div>
          </div>,
          document.body,
        )}

      {/* Barra flutuante da seleção de PJ — fixa no rodapé, sempre acessível */}
      {modoSelecao &&
        !movendo &&
        createPortal(
          <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40">
            <div className="flex items-center gap-3 bg-white border border-slate-200 rounded-2xl shadow-xl px-4 py-3">
              <span className="text-xs font-bold text-brand-950 whitespace-nowrap">
                {selecionados.size} colaborador(es) selecionado(s)
              </span>
              <button
                onClick={processarSelecaoPJ}
                disabled={selecionados.size === 0}
                className="flex items-center gap-1.5 text-xs font-bold text-white bg-brand-900 hover:bg-brand-950 rounded-xl px-4 py-2 shadow-md shadow-brand-950/10 transition-all cursor-pointer disabled:opacity-50 whitespace-nowrap"
              >
                <Briefcase className="h-4 w-4" /> Aplicar classificação PJ ({selecionados.size})
              </button>
              <button
                onClick={cancelarSelecao}
                className="text-xs font-semibold text-slate-500 hover:text-slate-700 cursor-pointer px-2"
              >
                Cancelar
              </button>
            </div>
          </div>,
          document.body,
        )}

      {/* Modal de auditoria do cálculo */}
      {auditando && <ModalAuditoria item={auditando} onClose={() => setAuditando(null)} />}

      {/* Modal: competência do TXT (coparticipação não a armazena) */}
      {exportEmpresa !== null && (
        <ModalCompetenciaTxt
          empresa={exportEmpresa}
          qtdPj={qtdPj}
          baixando={baixandoTxt}
          onCancelar={fecharExportTxt}
          onExportar={handleBaixarTxt}
        />
      )}

      {/* Modal: mover para PJ — perguntar se quer selecionar mais colaboradores */}
      {confirmandoPJ && (
        <ModalConfirmarPj
          cpf={confirmandoPJ.cpf}
          nome={confirmandoPJ.nome}
          onProcessarAgora={processarUm}
          onSelecionarMais={selecionarMais}
          onCancelar={() => setConfirmandoPJ(null)}
        />
      )}

      {/* Avisos (teto) */}
      {r.avisos.length > 0 && (
        <Secao titulo="Avisos" contador={r.avisos.length}>
          <div className="p-4 space-y-2">
            {r.avisos.map((a, i) => (
              <div
                key={i}
                className="bg-amber-50 border border-amber-200/60 p-3 rounded-xl text-xs text-amber-900 font-medium leading-relaxed"
              >
                {a}
              </div>
            ))}
          </div>
        </Secao>
      )}

      {/* Divergências */}
      {r.divergencias.length > 0 && (
        <Secao titulo="Divergências" contador={r.divergencias.length}>
          <div className="p-4 flex flex-col gap-2">
            {r.divergencias.map((d, i) => (
              <div
                key={i}
                className="border border-slate-200 p-3 rounded-xl flex items-start justify-between gap-3"
              >
                <div className="flex items-start gap-2.5 min-w-0">
                  {modoSelecao && ELEGIVEL_PJ.has(d.tipo) && d.cpf && (
                    <input
                      type="checkbox"
                      checked={selecionados.has(d.cpf)}
                      onChange={() => toggleSel(d.cpf)}
                      className="cursor-pointer mt-0.5 shrink-0"
                    />
                  )}
                  <ShieldAlert className="h-4 w-4 text-rose-400 shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200 mr-2">
                      {ROTULO_DIVERGENCIA[d.tipo] || d.tipo}
                    </span>
                    {d.nome && <span className="text-xs font-bold text-slate-900">{d.nome}</span>}
                    <span className="text-xs text-slate-600 block mt-0.5">
                      {d.descricao}
                      {d.num_eventos ? ` (${d.num_eventos} evento(s))` : ''}
                    </span>
                  </div>
                </div>
                {!somenteLeitura && ELEGIVEL_PJ.has(d.tipo) && d.cpf && (
                  <div className="relative shrink-0">
                    <button
                      onClick={() => setMenuAberto((m) => (m === `div-${i}` ? null : `div-${i}`))}
                      className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-700 cursor-pointer"
                      title="Ações"
                    >
                      <MoreVertical className="h-4 w-4" />
                    </button>
                    {menuAberto === `div-${i}` && (
                      <div className="absolute right-0 top-8 z-20 w-44 bg-white border border-slate-200 rounded-xl shadow-lg py-1 text-left">
                        <button
                          onClick={() => {
                            setMenuAberto(null);
                            iniciarPJ(d.cpf, d.nome);
                          }}
                          disabled={movendo === d.cpf}
                          className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 cursor-pointer disabled:opacity-50"
                          title="Classificar como PJ (aplica o salário padrão; deixa de consultar a API)"
                        >
                          <Briefcase className="h-3.5 w-3.5 text-slate-400" /> Mover para PJ
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Secao>
      )}

      {/* Confirmação FLUTUANTE no canto inferior direito: com o detalhamento
          expandido, a lista fica longa e o botão no fim da página exigia rolar
          todos os registros. Escondido no modo de seleção de PJ para não colidir
          com a barra flutuante daquele fluxo. */}
      {!somenteLeitura &&
        !modoSelecao &&
        createPortal(
          <div className="fixed bottom-6 right-6 z-40">
            {/* Chamada em arrow: `onClick={onConfirmSend}` passaria o evento de
              clique como snapshot, e o modal receberia um MouseEvent em vez do
              resultado (sem `itens`, quebrava na renderização). */}
            <button
              onClick={() => onConfirmSend()}
              disabled={total_itens === 0}
              title="Revise as divergências antes de confirmar. Registra a execução no histórico e lança o desconto na folha de cada colaborador no ERP; a competência da folha é informada na confirmação."
              className="flex items-center gap-2 py-3 px-6 bg-emerald-600 hover:bg-emerald-700 text-white rounded-2xl text-xs font-bold shadow-xl shadow-emerald-950/20 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Confirmar e lançar desconto
            </button>
          </div>,
          document.body,
        )}
    </div>
  );
}
