import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Toast } from '../types';
import * as api from '../api';
import { ApiError, Execucao, RespostaProcessamento, Resultado } from '../api';
import {
  FileDown,
  Search,
  RefreshCw,
  Calendar,
  Filter,
  Send,
  ChevronRight,
  Loader2,
  Building2,
  Eye,
  ArrowLeft,
  Mail,
  MoreVertical,
  FileText,
  Receipt,
  FileSpreadsheet,
  File,
} from 'lucide-react';
import EnvioErpModal from './EnvioErpModal';
import ResultScreen from './ResultScreen';
import CoparticipacaoResultScreen from './CoparticipacaoResultScreen';
import ClaroResultScreen from './ClaroResultScreen';
import Dropdown from './Dropdown';

// Ícone por categoria do documento (nf/boleto/planilha), com fallback genérico.
const ICONE_CATEGORIA = { nf: FileText, boleto: Receipt, planilha: FileSpreadsheet } as const;
function IconeDoc({ categoria }: { categoria: string }) {
  const Icone = ICONE_CATEGORIA[categoria as keyof typeof ICONE_CATEGORIA] ?? File;
  return <Icone className="h-3.5 w-3.5 text-slate-400 shrink-0" />;
}

interface HistoryScreenProps {
  addToast: (message: string, type: Toast['type']) => void;
  /** Rateio a filtrar na abertura (botão "Histórico" do card do dashboard). */
  tipoInicial?: string;
}

const ROTULO_STATUS: Record<string, { texto: string; cls: string }> = {
  enviado: { texto: 'Enviado', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  // Parte do lote entrou na folha: não é erro (a maioria passou) nem pendente.
  parcial: { texto: 'Concluído parcialmente', cls: 'bg-sky-50 text-sky-700 border-sky-200' },
  erro_envio: { texto: 'Erro no envio', cls: 'bg-rose-50 text-rose-700 border-rose-200' },
  pendente_envio: {
    texto: 'Pendente de envio',
    cls: 'bg-amber-50 text-amber-700 border-amber-200',
  },
};

/** Conta do documento quando o envio é por documento (telefonia: um título por
 *  boleto). Sem ela, sete lançamentos na mesma empresa viram sete linhas
 *  idênticas na tela e parecem duplicados. */
function Conta({ referencia }: { referencia?: string }) {
  if (!referencia) return null;
  return <span className="text-slate-400 whitespace-nowrap">conta {referencia}</span>;
}

function tituloTipo(tipo: string): string {
  return api.nomeRateio(tipo);
}
function moeda(v: string | number): string {
  return Number(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}
function dataHora(iso: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d
    .toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
    .replace(',', '');
}
function competenciaLegivel(c: string): string {
  if (c && c.length === 6) return `${c.slice(4)}/${c.slice(0, 4)}`;
  return c || '—';
}

/**
 * Menu de ações da linha (ícone ⋮). Renderiza o dropdown via portal, posicionado
 * a partir do retângulo do botão, para não ser cortado pelo overflow da tabela.
 */
function RowMenu({ children }: { children: (fechar: () => void) => ReactNode }) {
  const [aberto, setAberto] = useState(false);
  const [pos, setPos] = useState<{ top: number; right: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  const alternar = () => {
    if (aberto) {
      setAberto(false);
      return;
    }
    const r = btnRef.current?.getBoundingClientRect();
    if (r) setPos({ top: r.bottom + 4, right: window.innerWidth - r.right });
    setAberto(true);
  };
  const fechar = () => setAberto(false);

  return (
    <>
      <button
        ref={btnRef}
        onClick={alternar}
        title="Ações"
        className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-colors cursor-pointer"
      >
        <MoreVertical className="h-4 w-4" />
      </button>
      {aberto &&
        pos &&
        createPortal(
          <>
            <div className="fixed inset-0 z-40" onClick={fechar} />
            <div
              style={{ top: pos.top, right: pos.right }}
              className="fixed z-50 w-52 bg-white border border-slate-200 rounded-xl shadow-lg py-1 text-left animate-fade-in"
            >
              {children(fechar)}
            </div>
          </>,
          document.body,
        )}
    </>
  );
}

function MenuItem({
  icon: Icon,
  onClick,
  disabled,
  children,
}: {
  icon: typeof Eye;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed text-left"
    >
      <Icon className="h-3.5 w-3.5 text-slate-400 shrink-0" /> {children}
    </button>
  );
}

export default function HistoryScreen({ addToast, tipoInicial }: HistoryScreenProps) {
  const [execucoes, setExecucoes] = useState<Execucao[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [busca, setBusca] = useState('');
  const [statusFiltro, setStatusFiltro] = useState('Todos');
  const [tipoFiltro, setTipoFiltro] = useState(tipoInicial ?? 'Todos');
  const [expandida, setExpandida] = useState<number | null>(null);
  const [modalExec, setModalExec] = useState<Execucao | null>(null);
  const [detalhe, setDetalhe] = useState<Execucao | null>(null);

  const abrirDetalhe = async (id: number) => {
    try {
      setDetalhe(await api.getExecucao(id));
    } catch (err) {
      addToast(err instanceof ApiError ? err.message : 'Falha ao abrir o detalhe.', 'error');
    }
  };

  const recarregar = () =>
    api
      .listarExecucoes()
      .then(setExecucoes)
      .catch((err) =>
        addToast(err instanceof ApiError ? err.message : 'Falha ao carregar o histórico.', 'error'),
      );

  useEffect(() => {
    recarregar().finally(() => setCarregando(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // O dashboard pode pedir outro rateio sem desmontar a tela: ao mudar a prop,
  // o filtro acompanha já neste render (sem efeito e sem render intermediário).
  const [tipoInicialAnterior, setTipoInicialAnterior] = useState(tipoInicial);
  if (tipoInicial !== tipoInicialAnterior) {
    setTipoInicialAnterior(tipoInicial);
    setTipoFiltro(tipoInicial ?? 'Todos');
  }

  // Rateios com execução gravada — o filtro só oferece o que existe no histórico.
  const tiposPresentes = useMemo(
    () =>
      [...new Set<string>(execucoes.map((e) => e.tipo))].sort((a, b) =>
        tituloTipo(a).localeCompare(tituloTipo(b), 'pt-BR'),
      ),
    [execucoes],
  );

  const filtradas = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return execucoes.filter((e) => {
      const casaBusca =
        !q ||
        competenciaLegivel(e.competencia).toLowerCase().includes(q) ||
        e.usuario.toLowerCase().includes(q) ||
        tituloTipo(e.tipo).toLowerCase().includes(q);
      const casaStatus = statusFiltro === 'Todos' || e.status === statusFiltro;
      const casaTipo = tipoFiltro === 'Todos' || e.tipo === tipoFiltro;
      return casaBusca && casaStatus && casaTipo;
    });
  }, [execucoes, busca, statusFiltro, tipoFiltro]);

  const baixar = async (execId: number, docId: number, nome: string) => {
    try {
      await api.baixarDocumentoExecucao(execId, docId, nome);
    } catch (err) {
      addToast(err instanceof ApiError ? err.message : 'Falha ao baixar o documento.', 'error');
    }
  };

  const fecharModal = (atualizada?: Execucao) => {
    setModalExec(null);
    if (atualizada) recarregar();
  };

  const [notificando, setNotificando] = useState<number | null>(null);
  const notificarFiscal = async (id: number) => {
    setNotificando(id);
    try {
      const r = await api.notificarFiscal(id);
      addToast(`E-mail enviado ao fiscal (${r.destinatarios.join(', ')}).`, 'success');
      await recarregar();
    } catch (err) {
      addToast(err instanceof ApiError ? err.message : 'Falha ao enviar ao fiscal.', 'error');
    } finally {
      setNotificando(null);
    }
  };

  // Detalhe completo (consulta): reaproveita as telas de resultado em modo leitura.
  if (detalhe) {
    const resposta: RespostaProcessamento = {
      tipo: detalhe.tipo,
      alertas_validacao: [],
      total_itens: detalhe.resultado?.itens?.length ?? 0,
      pode_auditar: detalhe.pode_auditar,
      resultado: (detalhe.resultado ?? {
        itens: [],
        agregado: [],
        divergencias: [],
        estornos: [],
        reconciliacao: [],
        totais: [],
        avisos: [],
      }) as Resultado,
    };
    const comp = competenciaLegivel(detalhe.competencia);
    return (
      <div className="space-y-4 animate-fade-in">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setDetalhe(null)}
            className="flex items-center gap-1.5 py-2 px-3 border border-slate-200 bg-white rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Voltar ao histórico
          </button>
          <span className="text-xs text-slate-400">Somente leitura</span>
        </div>
        {detalhe.tipo === api.TIPO_COPARTICIPACAO ? (
          <CoparticipacaoResultScreen
            execucaoId={detalhe.id}
            tipo={detalhe.tipo}
            competence={comp}
            resposta={resposta}
            onBackToFlow={() => {}}
            onConfirmSend={() => {}}
            onReprocessar={async () => {}}
            addToast={addToast}
            somenteLeitura
          />
        ) : detalhe.tipo === api.TIPO_CLARO ? (
          /* O snapshot da telefonia é boletos/linhas, não itens/agregado: o
             ResultScreen não sabe lê-lo (era a tela branca na consulta). */
          <ClaroResultScreen
            titulosPorConta={Object.fromEntries(
              detalhe.envios
                .filter((e) => e.referencia && e.titulo)
                .map((e) => [e.referencia, e.titulo]),
            )}
            tipo={detalhe.tipo}
            competence={comp}
            resposta={resposta}
            onBackToFlow={() => {}}
            onConfirmSend={() => {}}
            onReprocessar={async () => {}}
            addToast={addToast}
            somenteLeitura
          />
        ) : (
          <ResultScreen
            execucaoId={detalhe.id}
            tipo={detalhe.tipo}
            competence={comp}
            resposta={resposta}
            addToast={addToast}
            somenteLeitura
          />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Histórico de execuções</h1>
        </div>
        <button
          onClick={recarregar}
          className="flex items-center gap-1.5 py-2 px-3 border border-slate-200 bg-white rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Atualizar
        </button>
      </div>

      {/* Filtros */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-4 shadow-sm flex flex-col md:flex-row gap-3 items-center justify-between">
        <div className="relative w-full md:max-w-xs">
          <Search className="h-4 w-4 text-slate-400 absolute inset-y-0 left-3 my-auto" />
          <input
            type="text"
            placeholder="Buscar por competência, usuário ou rateio…"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            className="block w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium placeholder-slate-400 text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 transition-all"
          />
        </div>
        <div className="flex flex-wrap gap-2.5 w-full md:w-auto items-center">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 shrink-0">
            <Filter className="h-3.5 w-3.5" /> <span>Rateio:</span>
          </div>
          <Dropdown
            value={tipoFiltro}
            onChange={setTipoFiltro}
            larguraMenu="w-72"
            opcoes={[
              { value: 'Todos', label: 'Todos' },
              ...tiposPresentes.map((t) => ({ value: t, label: tituloTipo(t) })),
            ]}
          />
          <span className="text-xs font-semibold text-slate-500 shrink-0">Status:</span>
          <Dropdown
            value={statusFiltro}
            onChange={setStatusFiltro}
            larguraMenu="w-48"
            opcoes={[
              { value: 'Todos', label: 'Todos' },
              { value: 'pendente_envio', label: 'Pendente de envio' },
              { value: 'enviado', label: 'Enviado' },
              { value: 'erro_envio', label: 'Erro no envio' },
            ]}
          />
        </div>
      </div>

      {/* Tabela */}
      <div className="bg-white rounded-2xl border border-slate-200/80 overflow-hidden shadow-sm">
        {carregando ? (
          <div className="py-16 flex items-center justify-center text-slate-400">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        ) : filtradas.length === 0 ? (
          <div className="py-12 text-center text-slate-400 text-sm">
            Nenhuma execução encontrada.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 text-slate-400 font-bold border-b border-slate-100 text-[10px] uppercase tracking-wider">
                  <th className="py-4 px-5">Nº Processo</th>
                  <th className="py-4 px-4">Competência</th>
                  <th className="py-4 px-4">Rateio</th>
                  <th className="py-4 px-4">Data/Hora</th>
                  <th className="py-4 px-4">Usuário</th>
                  <th className="py-4 px-4 text-right">Total</th>
                  <th className="py-4 px-4 text-center">Status</th>
                  <th className="py-4 px-5 text-center">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {filtradas.map((e) => {
                  const st = ROTULO_STATUS[e.status] || {
                    texto: e.status,
                    cls: 'bg-slate-100 text-slate-600 border-slate-200',
                  };
                  const aberta = expandida === e.id;
                  const lancaErp = api.lancaNoErp(e.tipo);
                  // Desconto em folha não gera título/AE nem notifica o fiscal —
                  // os rótulos e as ações da linha mudam conforme o processo.
                  const notificaFiscal = api.notificaFiscal(e.tipo);
                  const descontoEmFolha = api.exigeCompetenciaPagamento(e.tipo);
                  return (
                    <Fragment key={e.id}>
                      <tr className="hover:bg-slate-50/50 transition-colors font-medium">
                        <td className="py-3.5 px-5 font-semibold text-slate-900">
                          <button
                            onClick={() => setExpandida(aberta ? null : e.id)}
                            className="flex items-center gap-2 cursor-pointer"
                          >
                            <ChevronRight
                              className={`h-4 w-4 text-slate-400 transition-transform ${aberta ? 'rotate-90' : ''}`}
                            />
                            <span className="font-mono text-slate-500">{api.processoId(e.id)}</span>
                          </button>
                        </td>
                        <td className="py-3.5 px-4 text-slate-600">
                          <span className="inline-flex items-center gap-1.5">
                            <Calendar className="h-4 w-4 text-slate-400" />
                            {competenciaLegivel(e.competencia)}
                          </span>
                        </td>
                        <td className="py-3.5 px-4 text-slate-600">{tituloTipo(e.tipo)}</td>
                        <td className="py-3.5 px-4 text-slate-500">{dataHora(e.criado_em)}</td>
                        <td className="py-3.5 px-4 font-semibold text-slate-800">{e.usuario}</td>
                        <td className="py-3.5 px-4 text-right font-mono font-bold text-slate-950">
                          {moeda(e.total)}
                        </td>
                        <td className="py-3.5 px-4 text-center">
                          <span
                            className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${st.cls}`}
                          >
                            {st.texto}
                          </span>
                        </td>
                        <td className="py-3.5 px-5 text-center">
                          <div className="flex justify-center">
                            <RowMenu>
                              {(fechar) => (
                                <>
                                  <MenuItem
                                    icon={Eye}
                                    onClick={() => {
                                      fechar();
                                      abrirDetalhe(e.id);
                                    }}
                                  >
                                    Consultar detalhamento
                                  </MenuItem>
                                  {lancaErp && e.status !== 'enviado' && (
                                    <MenuItem
                                      icon={Send}
                                      onClick={() => {
                                        fechar();
                                        setModalExec(e);
                                      }}
                                    >
                                      {descontoEmFolha
                                        ? e.status === 'erro_envio'
                                          ? 'Relançar na folha'
                                          : 'Lançar na folha'
                                        : e.status === 'erro_envio'
                                          ? 'Reenviar ao ERP'
                                          : 'Enviar ao ERP'}
                                    </MenuItem>
                                  )}
                                  {notificaFiscal &&
                                    e.envios.some((x) => x.status === 'enviado') && (
                                      <MenuItem
                                        icon={Mail}
                                        disabled={notificando === e.id}
                                        onClick={() => {
                                          fechar();
                                          notificarFiscal(e.id);
                                        }}
                                      >
                                        {e.notificado_em
                                          ? 'Reenviar ao fiscal'
                                          : 'Notificar fiscal'}
                                      </MenuItem>
                                    )}
                                </>
                              )}
                            </RowMenu>
                          </div>
                        </td>
                      </tr>
                      {aberta && (
                        <tr className="bg-slate-50/40">
                          <td colSpan={8} className="px-5 py-4">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              {/* Documentos */}
                              <div>
                                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-2">
                                  Documentos ({e.documentos.length})
                                </div>
                                <div className="flex flex-wrap gap-2">
                                  {e.documentos.map((d) => (
                                    <button
                                      key={d.id}
                                      onClick={() => baixar(e.id, d.id, d.nome)}
                                      title={`Baixar ${d.nome}`}
                                      className="group flex items-center gap-1.5 py-1.5 px-2.5 max-w-[190px] bg-white border border-slate-200 rounded-lg text-[11px] font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
                                    >
                                      <IconeDoc categoria={d.categoria} />
                                      <span className="truncate">{d.nome}</span>
                                      <FileDown className="h-3.5 w-3.5 text-slate-300 group-hover:text-slate-500 shrink-0" />
                                    </button>
                                  ))}
                                  {e.documentos.length === 0 && (
                                    <span className="text-[11px] text-slate-400">
                                      Nenhum documento.
                                    </span>
                                  )}
                                </div>
                              </div>
                              {/* Notificação: a quem foi. Os cadastros mudam, e o
                                  registro é do momento do envio. */}
                              {e.notificado_para && e.notificado_para.para.length > 0 && (
                                <div>
                                  <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-2">
                                    Notificação ao fiscal
                                  </div>
                                  <p className="text-[11px] text-slate-600">
                                    <span className="font-semibold text-slate-700">Para: </span>
                                    {e.notificado_para.para.join(', ')}
                                    {e.notificado_para.copia.length > 0 && (
                                      <>
                                        {' · '}
                                        <span className="font-semibold text-slate-700">
                                          Cópia:{' '}
                                        </span>
                                        {e.notificado_para.copia.join(', ')}
                                      </>
                                    )}
                                  </p>
                                </div>
                              )}
                              {/* Envios ao ERP */}
                              <div>
                                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-2">
                                  {descontoEmFolha ? 'Lançamentos em folha' : 'Envios ao ERP'} (
                                  {e.envios.length})
                                </div>
                                <div className="space-y-1.5">
                                  {e.envios.map((env, i) => (
                                    <div key={i} className="flex items-start gap-2 text-[11px]">
                                      <Building2 className="h-3.5 w-3.5 text-slate-400 mt-0.5 shrink-0" />
                                      <span className="font-semibold text-slate-700 shrink-0">
                                        {env.empresa}
                                      </span>
                                      <Conta referencia={env.referencia} />
                                      {env.status === 'enviado' ? (
                                        // Sem título no desconto em folha: o retorno útil é a
                                        // confirmação do ERP (nº de matrículas incluídas).
                                        <span
                                          className={`text-emerald-700 min-w-0 ${env.titulo ? 'font-mono' : ''}`}
                                        >
                                          {env.titulo
                                            ? `Título ${env.titulo}`
                                            : env.mensagem || 'Enviado'}
                                        </span>
                                      ) : env.status === 'parcial' ? (
                                        <span className="text-sky-700 min-w-0">
                                          {env.aceitos} de {env.enviados} incluída(s)
                                          {env.matriculas_pendentes?.length
                                            ? ` · ${env.matriculas_pendentes.length} pendente(s): ${env.matriculas_pendentes
                                                .map((pe) => `${pe.nome || 'mat'} ${pe.matricula}`)
                                                .join(', ')}`
                                            : ' · pendentes não identificadas pelo ERP'}
                                        </span>
                                      ) : env.status === 'enviando' ? (
                                        // Só sobra assim quando o envio caiu entre o POST e a
                                        // resposta: não é erro nem sucesso, e o próximo envio
                                        // pede a conferência no ERP antes de repetir.
                                        <span className="text-amber-700 min-w-0">
                                          Envio interrompido antes da resposta do ERP
                                          {env.referencia ? ` · conta ${env.referencia}` : ''} ·
                                          confira no Protheus se o título entrou antes de reenviar
                                        </span>
                                      ) : env.status === 'pendente' ? (
                                        <span className="text-amber-600">Pendente (pré-nota)</span>
                                      ) : (
                                        <span className="text-rose-600 whitespace-pre-wrap break-words min-w-0">
                                          {env.mensagem}
                                        </span>
                                      )}
                                    </div>
                                  ))}
                                  {e.envios.length === 0 && (
                                    <span className="text-[11px] text-slate-400">
                                      {descontoEmFolha
                                        ? 'Ainda não lançado na folha.'
                                        : 'Ainda não enviado ao ERP.'}
                                    </span>
                                  )}
                                </div>
                              </div>
                            </div>
                            {/* Histórico de tentativas de envio (só quando houve erro/retentativa) */}
                            {api.historicoRelevante(e.tentativas) && (
                              <div className="mt-4">
                                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-2">
                                  Histórico de tentativas ({e.tentativas.length})
                                </div>
                                <div className="space-y-1">
                                  {e.tentativas.map((t) => {
                                    const ok = t.status === 'enviado';
                                    const pend = t.status === 'pendente';
                                    const borda = ok
                                      ? 'border-emerald-300'
                                      : pend
                                        ? 'border-amber-300'
                                        : 'border-rose-300';
                                    return (
                                      <div
                                        key={t.id}
                                        className={`border-l-2 ${borda} pl-2.5 py-0.5 text-[11px]`}
                                      >
                                        <div className="flex items-center gap-2 flex-wrap">
                                          <span className="font-mono text-slate-400 whitespace-nowrap">
                                            {dataHora(t.criado_em)}
                                          </span>
                                          <span className="font-semibold text-slate-700">
                                            {t.empresa}
                                          </span>
                                          <Conta referencia={t.referencia} />
                                          {ok ? (
                                            t.titulo ? (
                                              <span className="font-mono font-bold text-emerald-700">
                                                Título {t.titulo}
                                              </span>
                                            ) : (
                                              <span className="font-semibold text-emerald-700">
                                                enviado
                                              </span>
                                            )
                                          ) : pend ? (
                                            <span className="font-semibold text-amber-700">
                                              pendente
                                            </span>
                                          ) : (
                                            <span className="font-semibold text-rose-700">
                                              erro
                                            </span>
                                          )}
                                          {t.usuario && (
                                            <span className="text-slate-400">· {t.usuario}</span>
                                          )}
                                        </div>
                                        {t.mensagem && !pend && (!ok || !t.titulo) && (
                                          <p
                                            className={`mt-0.5 whitespace-pre-wrap break-words ${ok ? 'text-emerald-700' : 'text-rose-600'}`}
                                          >
                                            {t.mensagem}
                                          </p>
                                        )}
                                        {/* Corpo bruto da resposta: quando o ERP aceita
                                            parte do lote, é aqui que está (ou se prova
                                            que ele não informou quais registros). */}
                                        {t.resposta_erp != null && (
                                          <details className="mt-1">
                                            <summary className="cursor-pointer text-slate-500 hover:text-slate-700">
                                              Resposta do ERP
                                            </summary>
                                            <pre className="mt-1 max-h-48 overflow-auto rounded-lg bg-slate-900/95 p-2 text-[10px] leading-relaxed text-slate-100 whitespace-pre-wrap break-words">
                                              {JSON.stringify(t.resposta_erp, null, 2)}
                                            </pre>
                                          </details>
                                        )}
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modalExec && (
        <EnvioErpModal execucao={modalExec} onClose={fecharModal} addToast={addToast} />
      )}
    </div>
  );
}
