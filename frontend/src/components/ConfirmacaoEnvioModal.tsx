import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  X,
  Loader2,
  CheckCircle2,
  XCircle,
  Circle,
  MinusCircle,
  Database,
  Building2,
  Mail,
  ArrowRight,
  ShieldAlert,
  Clock,
  ChevronRight,
} from 'lucide-react';
import * as api from '../api';
import { ApiError, Resultado, EnvioResposta, TentativaEnvio } from '../api';
import { Toast } from '../types';

type StepStatus = 'pending' | 'running' | 'done' | 'partial' | 'error' | 'skipped';

interface Props {
  tipo: string;
  competence: string;
  snapshot: Resultado;
  arquivos: File[];
  onClose: (gravou: boolean) => void;
  addToast: (message: string, type: Toast['type']) => void;
}

function dataHora(iso: string): string {
  if (!iso) return '—';
  return new Date(iso)
    .toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
    .replace(',', '');
}

function IconeStatus({ status }: { status: StepStatus }) {
  if (status === 'running')
    return <Loader2 className="h-5 w-5 text-brand-500 animate-spin shrink-0" />;
  if (status === 'done') return <CheckCircle2 className="h-5 w-5 text-emerald-500 shrink-0" />;
  // Parcial: parte entrou na folha — atenção, não falha.
  if (status === 'partial') return <CheckCircle2 className="h-5 w-5 text-sky-500 shrink-0" />;
  if (status === 'error') return <XCircle className="h-5 w-5 text-rose-500 shrink-0" />;
  if (status === 'skipped') return <MinusCircle className="h-5 w-5 text-slate-300 shrink-0" />;
  return <Circle className="h-5 w-5 text-slate-300 shrink-0" />;
}

// Etapa do fluxo: apenas ícone de status + título. O detalhe (erros, títulos,
// tentativas) fica na área "Controle de execução", colapsável.
function Passo({
  status,
  icon: Icon,
  titulo,
}: {
  status: StepStatus;
  icon: typeof Database;
  titulo: string;
}) {
  const apagado = status === 'pending' || status === 'skipped';
  return (
    <div className="flex items-center gap-3">
      <IconeStatus status={status} />
      <div
        className={`flex items-center gap-1.5 text-sm font-semibold ${apagado ? 'text-slate-400' : 'text-slate-800'}`}
      >
        <Icon className={`h-3.5 w-3.5 ${apagado ? 'text-slate-300' : 'text-slate-400'}`} />
        {titulo}
        {status === 'skipped' && (
          <span className="text-[10px] font-bold uppercase text-slate-300">não se aplica</span>
        )}
      </div>
    </div>
  );
}

// Progresso do lançamento documento a documento (telefonia: um título por
// boleto). Alimentado pelo estado GRAVADO no servidor — o backend persiste cada
// título assim que o ERP responde —, então o que aparece aqui já existe no ERP,
// não é uma estimativa da tela.
function ProgressoDocumentos({
  envios,
  total,
}: {
  envios: api.EnvioErpResultado[];
  total: number;
}) {
  const documentos = envios.filter((e) => e.referencia);
  const concluidos = documentos.filter((e) => e.status === 'enviado' || e.status === 'erro').length;
  const pct = total > 0 ? Math.min(100, Math.round((concluidos / total) * 100)) : 0;
  return (
    <div className="ml-8 space-y-2">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] font-semibold text-slate-600 tabular-nums">
          {concluidos} de {total} boleto(s) lançado(s)
        </p>
      </div>
      <div className="h-1 rounded-full bg-slate-100 overflow-hidden">
        <div
          className="h-full bg-brand-500 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      {documentos.length > 0 && (
        <ul className="space-y-1">
          {documentos.map((e) => (
            <li
              key={`${e.empresa}|${e.referencia}`}
              className="flex items-start gap-1.5 text-[11px]"
            >
              {e.status === 'enviado' ? (
                <CheckCircle2 className="h-3.5 w-3.5 shrink-0 mt-px text-emerald-500" />
              ) : e.status === 'erro' ? (
                <XCircle className="h-3.5 w-3.5 shrink-0 mt-px text-rose-500" />
              ) : (
                <Loader2 className="h-3.5 w-3.5 shrink-0 mt-px text-brand-500 animate-spin" />
              )}
              <span className={e.status === 'erro' ? 'text-rose-700' : 'text-slate-600'}>
                {e.status === 'enviado' ? (
                  <>
                    Título{' '}
                    <strong className="font-semibold text-slate-800">{e.titulo || '—'}</strong> ·
                    conta {e.referencia}
                  </>
                ) : e.status === 'erro' ? (
                  <>Conta {e.referencia}: não lançada</>
                ) : (
                  <>Conta {e.referencia} · aguardando a resposta do ERP</>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function ConfirmacaoEnvioModal({
  tipo,
  competence,
  snapshot,
  arquivos,
  onClose,
  addToast,
}: Props) {
  const lancaErp = api.lancaNoErp(tipo);
  // Lançar no ERP não implica notificar o fiscal (telefonia e coparticipação não
  // têm NF), nem toda rotina gera título (desconto em folha não gera).
  const notificaFiscal = api.notificaFiscal(tipo);
  const exigeCompPagamento = api.exigeCompetenciaPagamento(tipo);
  // Telefonia: a unidade do lançamento é o boleto (um título cada), não a empresa.
  const tituloPorDocumento = api.umTituloPorDocumento(tipo);
  const [fase, setFase] = useState<'confirmar' | 'executando' | 'fim'>('confirmar');
  const [stHist, setStHist] = useState<StepStatus>('pending');
  const [stErp, setStErp] = useState<StepStatus>(lancaErp ? 'pending' : 'skipped');
  const [stFiscal, setStFiscal] = useState<StepStatus>(notificaFiscal ? 'pending' : 'skipped');
  // Competência da FOLHA em que o desconto entra (AAAA-MM no input; AAAAMM na API).
  const [compPagamento, setCompPagamento] = useState('');
  const [bloqueios, setBloqueios] = useState<string[]>([]);
  const [tentativas, setTentativas] = useState<TentativaEnvio[]>([]);
  // Envios por empresa da última resposta: é deles que sai o resumo do parcial.
  const [envios, setEnvios] = useState<api.EnvioErpResultado[]>([]);
  const [erroPasso, setErroPasso] = useState('');
  const [fiscalMsg, setFiscalMsg] = useState('');
  const [execId, setExecId] = useState<number | null>(null);
  // Abertura manual do controle de execução; null = usa o padrão (abre se houver erro).
  const [controleManual, setControleManual] = useState<boolean | null>(null);
  // Progresso do envio: quantos documentos este rateio lança um a um e o estado
  // já gravado de cada um. Só a telefonia tem contagem (> 1 boleto).
  const totalDocumentos = useMemo(() => api.qtdDocumentos(tipo, snapshot), [tipo, snapshot]);
  const [progresso, setProgresso] = useState<api.EnvioErpResultado[]>([]);
  // Quem vai receber a notificação, resolvido no backend (fiscal + cópia da
  // área). Mostrado ANTES de confirmar: sem isso o operador dispara sem saber
  // quem recebe, e "por que a TI recebeu?" não tem resposta na tela.
  const [destinatarios, setDestinatarios] = useState<api.DestinatariosNotificacao | null>(null);
  const consultaRef = useRef<number | null>(null);
  const pararConsulta = () => {
    if (consultaRef.current !== null) {
      window.clearInterval(consultaRef.current);
      consultaRef.current = null;
    }
  };
  useEffect(() => pararConsulta, []);

  useEffect(() => {
    if (!notificaFiscal) return;
    api
      .destinatariosNotificacao(tipo)
      .then(setDestinatarios)
      .catch(() => setDestinatarios(null));
  }, [notificaFiscal, tipo]);

  // Tolerante a snapshot sem itens: preferimos o modal abrir com contagem zero a
  // derrubar a tela inteira por um acesso a `itens[0]`.
  const itensSnapshot = snapshot?.itens ?? [];
  // Competência gravada no histórico: no pagamento vem do detalhamento da
  // operadora (nos itens); no desconto em folha a única competência existente é a
  // de PAGAMENTO informada aqui — sem isso a execução ficava sem competência e
  // não havia registro de qual folha recebeu o desconto.
  const competenciaRaw = exigeCompPagamento
    ? compPagamento.replace(/\D/g, '')
    : itensSnapshot[0]?.competencia || competence || '';
  // Sem a competência da folha, o backend recusa o envio (422) — bloqueia antes.
  const podeConfirmar = !exigeCompPagamento || compPagamento.replace(/\D/g, '').length === 6;
  // Quem fica FORA do lançamento em folha (PJ ou teto atingido), contado por
  // pessoa: o snapshot tem um item por colaborador × operadora.
  const itensCopart: api.ItemCopartResultado[] =
    exigeCompPagamento && api.ehResultadoCopart(snapshot) ? snapshot.itens : [];
  const cpfsForaDoErp = new Set(
    itensCopart.filter((i) => i.bloqueado_envio ?? (i.pj || i.teto_aplicado)).map((i) => i.cpf),
  ).size;

  const rodarFiscal = async (id: number) => {
    setStFiscal('running');
    setFiscalMsg('');
    try {
      const f = await api.notificarFiscal(id);
      setStFiscal('done');
      setFiscalMsg(`Departamento fiscal notificado: ${f.destinatarios.join(', ')}.`);
    } catch (err) {
      setStFiscal('error');
      setFiscalMsg(err instanceof ApiError ? err.message : 'Falha ao notificar o fiscal.');
    }
  };

  // Envio ao ERP + fiscal (reutilizado no "tentar novamente"). Idempotente: empresas
  // já integradas não são reenviadas (não duplica título).
  const rodarErp = async (id: number) => {
    setStErp('running');
    setErroPasso('');
    setProgresso([]);
    // Enquanto o envio corre, consulta o estado gravado: cada título entra no
    // banco assim que o ERP responde, então o operador acompanha o avanço em vez
    // de olhar um passo parado por minutos.
    if (totalDocumentos > 1) {
      consultaRef.current = window.setInterval(() => {
        api
          .getExecucao(id)
          .then((atual) => setProgresso(atual.envios))
          .catch(() => {});
      }, 2000);
    }
    let r: EnvioResposta;
    try {
      r = await api.enviarExecucao(id, compPagamento.replace(/\D/g, '') || undefined);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      // 504/502/rede: o backend pode ter concluído — busca o estado real.
      if (status === 504 || status === 502 || status === 0) {
        try {
          const atual = await api.getExecucao(id);
          r = {
            bloqueado: false,
            bloqueios: [],
            alertas: [],
            status: atual.status,
            envios: atual.envios,
            tentativas: atual.tentativas,
          };
          addToast(
            'Tempo de resposta excedido no proxy. Estado real do envio recuperado do servidor.',
            'info',
          );
        } catch {
          setStErp('error');
          setErroPasso(
            'Tempo de resposta do servidor excedido. O envio pode ter sido concluído; consulte o histórico antes de reenviar.',
          );
          return;
        }
      } else {
        setStErp('error');
        setErroPasso(err instanceof ApiError ? err.message : 'Falha ao enviar ao ERP.');
        return;
      }
    } finally {
      pararConsulta();
    }
    setBloqueios(r.bloqueado ? (r.bloqueios ?? []) : []);
    setTentativas(r.tentativas ?? []);
    setEnvios(r.envios ?? []);
    if (r.status === 'enviado') {
      setStErp('done');
      if (notificaFiscal) await rodarFiscal(id);
    } else if (r.status === 'parcial') {
      // A maior parte entrou na folha; o reenvio manda SOMENTE as recusadas.
      setStErp('partial');
      setStFiscal('skipped');
      setErroPasso('');
    } else {
      setStErp('error');
      setStFiscal('skipped');
      setErroPasso(
        r.bloqueado
          ? 'Envio bloqueado pela trava anti-parcial. Resolva as pendências abaixo e repita o envio.'
          : 'Envio concluído com erros ou pendências. Consulte os detalhes abaixo e repita o envio.',
      );
    }
  };

  const iniciar = async () => {
    setFase('executando');
    setStHist('running');
    setErroPasso('');
    let exec: api.Execucao;
    try {
      exec = await api.confirmarExecucao(tipo, competenciaRaw, snapshot, arquivos);
      setExecId(exec.id);
      setStHist('done');
    } catch (err) {
      setStHist('error');
      setErroPasso(err instanceof ApiError ? err.message : 'Falha ao gravar no histórico.');
      setFase('fim');
      return;
    }
    if (lancaErp) await rodarErp(exec.id);
    setFase('fim');
  };

  const tentarNovamente = async () => {
    if (execId == null) return;
    setFase('executando');
    await rodarErp(execId);
    setFase('fim');
  };

  const reenviarFiscal = async () => {
    if (execId == null) return;
    setFase('executando');
    await rodarFiscal(execId);
    setFase('fim');
  };

  const fechar = () => onClose(execId !== null);

  // Sucesso total quando gravou e (coparticipação: só grava) ou (pagamento: ERP ok).
  const sucessoTotal = stHist === 'done' && (!lancaErp || stErp === 'done');
  const podeTentarErp = fase === 'fim' && (stErp === 'error' || stErp === 'partial');
  // Empresas com parte do lote recusada — é o que o reenvio vai tratar.
  // Empresas com registros recusados NOMEADOS — vale para parcial e para erro
  // total (um reenvio que falha inteiro também vem com a lista).
  const parciais = envios.filter(
    (e) => e.status === 'parcial' || (e.matriculas_pendentes?.length ?? 0) > 0,
  );
  // Totais do lote (todas as empresas): uma contagem só, em vez de uma por empresa.
  const enviadosTotal = envios.reduce((n, e) => n + (e.enviados ?? 0), 0);
  const aceitosTotal = envios.reduce((n, e) => n + (e.aceitos ?? 0), 0);
  const pendentes = parciais.flatMap((e) =>
    (e.matriculas_pendentes ?? []).map((p) => ({ ...p, empresa: e.empresa })),
  );
  const pendentesTotal = pendentes.length;
  // Agrupado por MOTIVO: o mesmo problema em várias pessoas é uma tratativa só.
  const motivosPendentes = [
    ...pendentes.reduce((mapa, p) => {
      const motivo = p.motivo || 'Recusado pelo ERP';
      mapa.set(motivo, [...(mapa.get(motivo) ?? []), p]);
      return mapa;
    }, new Map<string, Array<(typeof pendentes)[number]>>()),
  ];
  const podeReenviarFiscal = fase === 'fim' && stErp === 'done' && stFiscal === 'error';
  const temErro = stHist === 'error' || stErp === 'error';
  const temControle = !!erroPasso || bloqueios.length > 0 || tentativas.length > 0;
  const controleAberto = controleManual ?? temErro; // abre sozinho quando há erro

  return createPortal(
    <div
      className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={fechar}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl max-w-lg w-full max-h-[88vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Cabeçalho */}
        <div className="p-5 border-b border-slate-100 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="h-9 w-9 rounded-xl bg-brand-50 border border-brand-100 flex items-center justify-center shrink-0">
              <ArrowRight className="h-4.5 w-4.5 text-brand-900" />
            </div>
            <div className="min-w-0">
              <h3 className="text-sm font-bold text-slate-900">
                {fase === 'confirmar'
                  ? 'Confirmar e concluir'
                  : fase === 'fim'
                    ? sucessoTotal
                      ? 'Concluído'
                      : stErp === 'partial'
                        ? 'Concluído parcialmente'
                        : 'Processando'
                    : 'Processando'}
              </h3>
              {/* Só o que existe: a coparticipação não tem competência de eventos,
                  e "Competência —" é ruído. */}
              <p className="text-[11px] text-slate-500">
                {[
                  competence ? `Competência ${competence}` : '',
                  execId != null ? `Processo ${api.processoId(execId)}` : '',
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
            </div>
          </div>
          <button
            onClick={fechar}
            className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-5 overflow-y-auto space-y-4">
          {fase === 'confirmar' ? (
            <div className="space-y-3">
              {/* Só o efeito da ação, numa frase. O que este rateio NÃO faz
                  (título, fiscal) é natureza de outro processo — não é decisão de
                  quem está confirmando, e virava ruído aqui. */}
              <p className="text-xs text-slate-600 leading-relaxed">
                {exigeCompPagamento ? (
                  <>
                    Ao confirmar, a execução é gravada no histórico e o{' '}
                    <strong>desconto é lançado na folha</strong> de cada colaborador no ERP, por
                    empresa.
                  </>
                ) : tituloPorDocumento ? (
                  <>
                    Ao confirmar, a execução é gravada no histórico e é gerada uma{' '}
                    <strong>Autorização de Entrega por boleto</strong> no ERP
                    {notificaFiscal ? (
                      <>, com notificação ao departamento fiscal ao concluir</>
                    ) : null}
                    .
                  </>
                ) : lancaErp ? (
                  <>
                    Ao confirmar, a execução é gravada no histórico e os{' '}
                    <strong>títulos são gerados no ERP</strong> (uma AE ou pré-nota por empresa)
                    {notificaFiscal ? <>, com notificação ao departamento fiscal</> : null}.
                  </>
                ) : (
                  <>Ao confirmar, a execução e os documentos são gravados no histórico.</>
                )}
              </p>
              {notificaFiscal && destinatarios && destinatarios.para.length > 0 && (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-[11px] text-slate-600 space-y-0.5">
                  <p>
                    <span className="font-semibold text-slate-700">Para: </span>
                    {destinatarios.para.join(', ')}
                  </p>
                  {destinatarios.copia.length > 0 && (
                    <p>
                      <span className="font-semibold text-slate-700">Cópia: </span>
                      {destinatarios.copia.join(', ')}
                    </p>
                  )}
                </div>
              )}
              {exigeCompPagamento && (
                <label className="block">
                  <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                    Competência de pagamento <span className="text-rose-500">*</span>
                  </span>
                  <input
                    type="month"
                    value={compPagamento}
                    onChange={(e) => setCompPagamento(e.target.value)}
                    className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-800 focus:border-brand-400 focus:outline-none"
                  />
                  <span className="mt-1 block text-[11px] text-slate-500">
                    Folha em que o desconto será lançado.
                  </span>
                </label>
              )}
              {/* Exceção que muda o trabalho de quem confirma: parte da relação
                  não vai ao ERP e precisa de tratativa manual. Uma linha. */}
              {exigeCompPagamento && cpfsForaDoErp > 0 && (
                <p className="text-[11px] text-slate-500">
                  {cpfsForaDoErp} colaborador(es) permanecem em tratativa manual (PJ ou teto) e não
                  serão enviados.
                </p>
              )}
            </div>
          ) : (
            <>
              {/* Stepper: apenas ícone + título. O detalhe fica no "Controle de execução". */}
              <div className="space-y-4">
                <Passo status={stHist} icon={Database} titulo="Armazenando rateio no histórico" />
                {lancaErp && (
                  <Passo
                    status={stErp}
                    icon={Building2}
                    titulo={
                      exigeCompPagamento
                        ? 'Lançando o desconto na folha (ERP)'
                        : 'Enviando títulos ao ERP'
                    }
                  />
                )}
                {lancaErp && totalDocumentos > 1 && (stErp === 'running' || stErp === 'error') && (
                  <ProgressoDocumentos envios={progresso} total={totalDocumentos} />
                )}
                {notificaFiscal && (
                  <Passo status={stFiscal} icon={Mail} titulo="Notificando o departamento fiscal" />
                )}
              </div>

              {/* Parcial: uma frase com o resultado, a lista de quem ficou de fora
                  agrupada por motivo, e o que o botão vai fazer. A mensagem técnica
                  do ERP (HTTP, "operação realizada com sucesso", contagens
                  repetidas) fica só no histórico — aqui ela confundia. */}
              {fase === 'fim' &&
                (stErp === 'partial' || (stErp === 'error' && pendentesTotal > 0)) && (
                  <div className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900 space-y-2">
                    <p className="flex items-start gap-2">
                      {aceitosTotal > 0 ? (
                        <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5 text-sky-500" />
                      ) : (
                        <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5 text-sky-500" />
                      )}
                      <span>
                        {aceitosTotal > 0 ? (
                          <>
                            <strong>
                              {aceitosTotal} de {enviadosTotal} lançamentos incluídos na folha.
                            </strong>
                            {pendentesTotal > 0 && (
                              <>
                                {' '}
                                {pendentesTotal} não {pendentesTotal === 1 ? 'entrou' : 'entraram'}.
                              </>
                            )}
                          </>
                        ) : (
                          <strong>Nenhum dos {enviadosTotal} lançamentos entrou na folha.</strong>
                        )}
                      </span>
                    </p>

                    {pendentesTotal > 0 ? (
                      <div className="pl-6 space-y-2">
                        {motivosPendentes.map(([motivo, pessoas]) => (
                          <div key={motivo}>
                            <p className="font-semibold">
                              {motivo} ({pessoas.length})
                            </p>
                            <ul className="mt-0.5 space-y-0.5">
                              {pessoas.map((pe) => (
                                <li key={`${pe.empresa}-${pe.matricula}`} className="flex gap-1.5">
                                  <span className="text-sky-400">·</span>
                                  <span>
                                    {pe.nome || 'Colaborador'}{' '}
                                    <span className="text-sky-700/70">
                                      — mat {pe.matricula} · {pe.empresa}
                                    </span>
                                  </span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        ))}
                        <p className="text-sky-800/80">
                          “Reenviar pendentes” envia somente{' '}
                          {pendentesTotal === 1 ? 'este registro' : `estes ${pendentesTotal}`}
                          {aceitosTotal > 0 ? '; os já incluídos não voltam.' : '.'}
                        </p>
                      </div>
                    ) : (
                      <p className="pl-6">
                        O ERP não informou quais registros recusou, então o reenvio automático fica
                        bloqueado — mandaria tudo de novo e duplicaria quem já entrou. Trate pelo
                        TXT ou manualmente.
                      </p>
                    )}
                  </div>
                )}

              {/* Sucesso total */}
              {fase === 'fim' && sucessoTotal && (
                <div className="flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">
                  <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5 text-emerald-500" />
                  <span>
                    {exigeCompPagamento ? (
                      <>
                        <strong>Concluído.</strong> Rateio gravado e desconto lançado na folha no
                        ERP.
                      </>
                    ) : lancaErp ? (
                      <>
                        <strong>Concluído.</strong> Rateio gravado, títulos criados no ERP
                        {stFiscal === 'done' ? ' e fiscal notificado' : ''}.
                      </>
                    ) : (
                      <>
                        <strong>Concluído.</strong> Rateio armazenado no histórico.
                      </>
                    )}
                  </span>
                </div>
              )}

              {/* Títulos criados mas fiscal falhou */}
              {fase === 'fim' && stErp === 'done' && stFiscal === 'error' && (
                <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
                  <Mail className="h-4 w-4 shrink-0 mt-0.5 text-rose-500" />
                  <span>
                    Títulos criados, mas o fiscal não foi notificado: {fiscalMsg} Use “Reenviar ao
                    fiscal”.
                  </span>
                </div>
              )}

              {/* Controle de execução (colapsável) — detalhe de erros, bloqueios e tentativas */}
              {temControle && (
                <div className="rounded-xl border border-slate-200 overflow-hidden">
                  <button
                    onClick={() => setControleManual(!controleAberto)}
                    className="w-full flex items-center gap-2 px-3 py-2.5 bg-slate-50 hover:bg-slate-100 transition-colors cursor-pointer text-left"
                  >
                    <ChevronRight
                      className={`h-4 w-4 text-slate-400 transition-transform ${controleAberto ? 'rotate-90' : ''}`}
                    />
                    <span className="text-xs font-bold text-slate-700">Controle de execução</span>
                    {temErro && (
                      <span className="text-[10px] font-bold uppercase text-rose-600 bg-rose-50 border border-rose-200 rounded px-1.5 py-0.5">
                        com erro
                      </span>
                    )}
                  </button>
                  {controleAberto && (
                    <div className="p-3 space-y-3 border-t border-slate-100">
                      {erroPasso && (
                        <div className="flex items-start gap-2 text-[11px] text-rose-700">
                          <XCircle className="h-3.5 w-3.5 shrink-0 mt-0.5 text-rose-500" />
                          <span>{erroPasso}</span>
                        </div>
                      )}
                      {bloqueios.map((b, i) => (
                        <div
                          key={i}
                          className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-800"
                        >
                          <ShieldAlert className="h-3.5 w-3.5 shrink-0 mt-0.5 text-amber-500" />
                          <span>{b}</span>
                        </div>
                      ))}
                      {tentativas.length > 0 && (
                        <div>
                          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                            <Clock className="h-3.5 w-3.5" /> Tentativas ({tentativas.length})
                          </div>
                          <div className="space-y-1.5">
                            {tentativas.map((t) => {
                              const ok = t.status === 'enviado';
                              const pend = t.status === 'pendente';
                              const borda = ok
                                ? 'border-emerald-300'
                                : pend
                                  ? 'border-amber-300'
                                  : 'border-rose-300';
                              return (
                                <div key={t.id} className={`border-l-2 ${borda} pl-2.5 py-0.5`}>
                                  <div className="flex items-center gap-2 flex-wrap text-[11px]">
                                    <span className="font-mono text-slate-400 whitespace-nowrap">
                                      {dataHora(t.criado_em)}
                                    </span>
                                    <span className="font-semibold text-slate-700">
                                      {t.empresa}
                                    </span>
                                    {/* Um título por boleto: sem a conta, as tentativas
                                        da mesma empresa ficam indistinguíveis. */}
                                    {t.referencia && (
                                      <span className="text-slate-400 whitespace-nowrap">
                                        conta {t.referencia}
                                      </span>
                                    )}
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
                                      <span className="font-semibold text-amber-700">pendente</span>
                                    ) : (
                                      <span className="font-semibold text-rose-700">erro</span>
                                    )}
                                    {t.usuario && (
                                      <span className="text-slate-400">· {t.usuario}</span>
                                    )}
                                  </div>
                                  {t.mensagem && !pend && (!ok || !t.titulo) && (
                                    <p
                                      className={`text-[11px] mt-0.5 whitespace-pre-wrap break-words ${ok ? 'text-emerald-700' : 'text-rose-600'}`}
                                    >
                                      {t.mensagem}
                                    </p>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Rodapé */}
        <div className="bg-slate-50 px-5 py-4 border-t border-slate-100 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
          {fase === 'confirmar' && (
            <>
              <button
                onClick={fechar}
                className="py-2.5 px-5 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer"
              >
                Cancelar
              </button>
              <button
                onClick={iniciar}
                disabled={!podeConfirmar}
                title={
                  podeConfirmar
                    ? undefined
                    : 'Informe a competência de pagamento (folha do desconto).'
                }
                className="flex items-center justify-center gap-1.5 py-2.5 px-5 bg-brand-900 hover:bg-brand-950 text-white rounded-xl text-xs font-bold shadow-md shadow-brand-950/10 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {lancaErp ? 'Confirmar e enviar' : 'Confirmar e gravar'}{' '}
                <ArrowRight className="h-4 w-4" />
              </button>
            </>
          )}
          {fase === 'executando' && (
            <button
              disabled
              className="flex items-center justify-center gap-1.5 py-2.5 px-5 bg-brand-900/60 text-white rounded-xl text-xs font-bold cursor-not-allowed"
            >
              <Loader2 className="h-4 w-4 animate-spin" /> Processando…
            </button>
          )}
          {fase === 'fim' && (
            <>
              <button
                onClick={fechar}
                className="py-2.5 px-5 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer"
              >
                {sucessoTotal ? 'Concluir' : 'Fechar'}
              </button>
              {podeTentarErp && (
                <button
                  onClick={tentarNovamente}
                  className="flex items-center justify-center gap-1.5 py-2.5 px-5 bg-brand-900 hover:bg-brand-950 text-white rounded-xl text-xs font-bold cursor-pointer"
                >
                  <Building2 className="h-4 w-4" />
                  {stErp === 'partial' ? 'Reenviar pendentes' : 'Tentar novamente'}
                </button>
              )}
              {podeReenviarFiscal && (
                <button
                  onClick={reenviarFiscal}
                  className="flex items-center justify-center gap-1.5 py-2.5 px-5 border border-brand-200 bg-white hover:bg-brand-50 text-brand-900 rounded-xl text-xs font-bold cursor-pointer"
                >
                  <Mail className="h-4 w-4" /> Reenviar ao fiscal
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
