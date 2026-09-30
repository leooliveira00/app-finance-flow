import { useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Building2,
  CheckCircle2,
  XCircle,
  ShieldAlert,
  Loader2,
  X,
  Send,
  Info,
  Clock,
  Mail,
} from 'lucide-react';
import * as api from '../api';
import { ApiError, Execucao, EnvioResposta } from '../api';
import { moeda } from '../formatacao';
import { Toast } from '../types';

interface Props {
  execucao: Execucao;
  onClose: (atualizada?: Execucao) => void;
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

export default function EnvioErpModal({ execucao, onClose, addToast }: Props) {
  // Desconto em folha (coparticipação): não gera título/AE nem notifica o fiscal.
  const notificaFiscal = api.notificaFiscal(execucao.tipo);
  const descontoEmFolha = api.exigeCompetenciaPagamento(execucao.tipo);
  const [enviando, setEnviando] = useState(false);
  const [resp, setResp] = useState<EnvioResposta | null>(null);
  const [erroModal, setErroModal] = useState('');
  // Fluxo do fiscal: notificado automaticamente após a conclusão dos títulos.
  const [fiscalStatus, setFiscalStatus] = useState<'idle' | 'enviando' | 'ok' | 'erro'>('idle');
  const [fiscalMsg, setFiscalMsg] = useState('');
  // Envios já existentes (reenvio a partir do histórico).
  const enviosIniciais = execucao.envios || [];

  const dispararFiscal = async (auto: boolean) => {
    setFiscalStatus('enviando');
    try {
      const r = await api.notificarFiscal(execucao.id);
      setFiscalStatus('ok');
      setFiscalMsg(`Departamento fiscal notificado: ${r.destinatarios.join(', ')}.`);
      if (!auto) addToast(`E-mail enviado ao fiscal (${r.destinatarios.join(', ')}).`, 'success');
    } catch (err) {
      const m = err instanceof ApiError ? err.message : 'Falha ao enviar ao fiscal.';
      setFiscalStatus('erro');
      setFiscalMsg(m);
      addToast(m, 'error');
    }
  };

  // Aplica o resultado do envio (do POST ou recuperado após timeout) e, se os
  // títulos concluíram, notifica o fiscal automaticamente.
  const aplicarResultado = async (r: EnvioResposta, recuperado: boolean) => {
    setResp(r);
    if (recuperado) {
      addToast(
        'Tempo de resposta excedido no proxy. Estado real do envio recuperado do servidor.',
        'info',
      );
    } else if (r.bloqueado) {
      addToast(
        'Envio bloqueado. Verifique as pendências; a execução foi gravada para reenvio.',
        'warning',
      );
    } else if (r.envios.some((e) => e.status === 'parcial')) {
      const pend = r.envios.reduce((n, e) => n + (e.matriculas_pendentes?.length ?? 0), 0);
      const aceitos = r.envios.reduce((n, e) => n + (e.aceitos ?? 0), 0);
      const total = r.envios.reduce((n, e) => n + (e.enviados ?? 0), 0);
      addToast(
        `${aceitos} de ${total} lançamentos incluídos na folha; ${pend} pendente(s) para reenvio.`,
        'warning',
      );
    } else if (r.envios.some((e) => e.status === 'erro')) {
      addToast('Envio concluído com erros. Salvo para reenvio.', 'warning');
    } else if (r.envios.some((e) => e.status === 'pendente')) {
      addToast('Enviado. Há empresa com rotina pendente (pré-nota).', 'info');
    } else {
      addToast(
        descontoEmFolha
          ? 'Desconto lançado na folha com sucesso.'
          : 'Lançamentos enviados ao ERP com sucesso.',
        'success',
      );
    }
    // Conclusão dos títulos (todas as empresas integradas): notifica o fiscal
    // automaticamente e dá o retorno de conclusão/falha ao usuário.
    if (
      notificaFiscal &&
      r.status === 'enviado' &&
      !execucao.notificado_em &&
      fiscalStatus === 'idle'
    ) {
      await dispararFiscal(true);
    }
  };

  const enviar = async () => {
    setEnviando(true);
    setErroModal('');
    try {
      const r = await api.enviarExecucao(execucao.id);
      await aplicarResultado(r, false);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      // 504/502 (gateway timeout) ou erro de rede: o backend PODE ter concluído
      // (o envio ao ERP é demorado). Busca o estado real em vez de deixar o
      // usuário no escuro — a idempotência garante que reenviar não duplica.
      if (status === 504 || status === 502 || status === 0) {
        try {
          const atual = await api.getExecucao(execucao.id);
          await aplicarResultado(
            {
              bloqueado: false,
              bloqueios: [],
              alertas: [],
              status: atual.status,
              envios: atual.envios,
              tentativas: atual.tentativas,
            },
            true,
          );
        } catch {
          setErroModal(
            'O servidor demorou a responder (tempo excedido). O envio pode ter continuado — atualize o histórico para confirmar o resultado antes de reenviar.',
          );
          addToast('Tempo de resposta excedido. Verifique o histórico.', 'warning');
        }
      } else {
        const msg = err instanceof ApiError ? err.message : 'Falha ao enviar ao ERP.';
        setErroModal(msg);
        addToast(msg, 'error');
      }
    } finally {
      setEnviando(false);
    }
  };

  const notificando = fiscalStatus === 'enviando';

  const envios = resp?.envios ?? enviosIniciais;
  const tentativas = resp?.tentativas ?? execucao.tentativas ?? [];
  const bloqueios = resp?.bloqueado ? (resp.bloqueios ?? []) : [];
  const alertas = resp?.alertas ?? [];
  const finalizado = resp !== null;
  const temEnviado = envios.some((e) => e.status === 'enviado');

  return createPortal(
    <div
      className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={() =>
        onClose(resp ? { ...execucao, status: resp.status, envios: resp.envios } : undefined)
      }
    >
      <div
        className="bg-white rounded-2xl shadow-2xl max-w-lg w-full max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-5 border-b border-slate-100 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="h-9 w-9 rounded-xl bg-brand-50 border border-brand-100 flex items-center justify-center shrink-0">
              <Send className="h-4.5 w-4.5 text-brand-900" />
            </div>
            <div className="min-w-0">
              <h3 className="text-sm font-bold text-slate-900">
                {descontoEmFolha ? 'Lançar desconto na folha' : 'Enviar ao ERP'}
              </h3>
              <p className="text-[11px] text-slate-500">
                {[
                  execucao.competencia ? `Competência ${execucao.competencia}` : '',
                  moeda(execucao.total),
                  `Processo ${api.processoId(execucao.id)}`,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
            </div>
          </div>
          <button
            onClick={() =>
              onClose(resp ? { ...execucao, status: resp.status, envios: resp.envios } : undefined)
            }
            className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-5 overflow-y-auto space-y-3">
          {/* Erro do próprio envio (rede/timeout sem recuperação) */}
          {erroModal && (
            <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
              <XCircle className="h-4 w-4 shrink-0 mt-0.5 text-rose-500" />
              <span>{erroModal}</span>
            </div>
          )}

          {!finalizado && bloqueios.length === 0 && envios.length === 0 && !erroModal && (
            <p className="text-xs text-slate-600 leading-relaxed">
              {descontoEmFolha ? (
                <>
                  O desconto será lançado na folha de cada colaborador, por empresa, na competência{' '}
                  {execucao.competencia || 'gravada na execução'}. Empresas já lançadas não são
                  reenviadas.
                </>
              ) : (
                <>
                  Serão criadas as Autorizações de Entrega (uma por empresa/NF), gerando os títulos
                  no ERP. Se faltar contrato em alguma empresa, <strong>nada é enviado</strong> e a
                  execução fica salva para reenvio.
                </>
              )}
            </p>
          )}

          {/* Bloqueios (trava anti-parcial) */}
          {bloqueios.length > 0 && (
            <div className="space-y-2">
              {bloqueios.map((b, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800"
                >
                  <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5 text-amber-500" />
                  <span>{b}</span>
                </div>
              ))}
              <p className="text-[11px] text-slate-500">
                Resolva as pendências no ERP e reenvie por aqui ou pelo histórico.
              </p>
            </div>
          )}

          {/* Alertas informativos (não bloqueiam) */}
          {alertas.length > 0 && (
            <div className="space-y-2">
              {alertas.map((a, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 rounded-xl border border-sky-200 bg-sky-50 p-3 text-xs text-sky-800"
                >
                  <Info className="h-4 w-4 shrink-0 mt-0.5 text-sky-500" />
                  <span>{a}</span>
                </div>
              ))}
            </div>
          )}

          {/* Resultado por empresa/título */}
          {envios.length > 0 && (
            <div className="space-y-2">
              {envios.map((e, i) => {
                const ok = e.status === 'enviado';
                const pendente = e.status === 'pendente';
                const parcial = e.status === 'parcial';
                const temPendentes = (e.matriculas_pendentes?.length ?? 0) > 0;
                const cls = ok
                  ? 'border-emerald-200 bg-emerald-50/50'
                  : parcial
                    ? 'border-sky-200 bg-sky-50/50'
                    : pendente
                      ? 'border-amber-200 bg-amber-50/50'
                      : 'border-rose-200 bg-rose-50/50';
                return (
                  <div key={i} className={`rounded-xl border p-3 ${cls}`}>
                    <div className="flex items-center gap-2">
                      {ok ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                      ) : parcial ? (
                        <CheckCircle2 className="h-4 w-4 text-sky-500" />
                      ) : pendente ? (
                        <Clock className="h-4 w-4 text-amber-500" />
                      ) : (
                        <XCircle className="h-4 w-4 text-rose-500" />
                      )}
                      <Building2 className="h-3.5 w-3.5 text-slate-400" />
                      <span className="text-xs font-bold text-slate-900">{e.empresa}</span>
                      {/* Telefonia: um lançamento por boleto na mesma empresa. */}
                      {e.referencia && (
                        <span className="text-[11px] text-slate-500 whitespace-nowrap">
                          conta {e.referencia}
                        </span>
                      )}
                      {ok && (
                        <span className="ml-auto text-[11px] font-bold text-emerald-700 bg-emerald-100 border border-emerald-200 px-2 py-0.5 rounded">
                          {e.titulo ? `Título ${e.titulo}` : e.mensagem || 'Enviado'}
                        </span>
                      )}
                      {(parcial || (!ok && !pendente && e.enviados)) && (
                        <span
                          className={`ml-auto text-[11px] font-bold px-2 py-0.5 rounded border ${
                            parcial
                              ? 'text-sky-700 bg-sky-100 border-sky-200'
                              : 'text-rose-700 bg-rose-100 border-rose-200'
                          }`}
                        >
                          {e.aceitos ?? 0} de {e.enviados} incluída(s)
                        </span>
                      )}
                      {pendente && (
                        <span className="ml-auto text-[10px] font-bold uppercase text-amber-600">
                          Pendente
                        </span>
                      )}
                      {!ok && !parcial && !pendente && (
                        <span className="ml-auto text-[10px] font-bold uppercase text-rose-600">
                          Erro
                        </span>
                      )}
                    </div>
                    {e.contrato && (
                      <p className="text-[11px] text-slate-500 mt-1">Contrato {e.contrato}</p>
                    )}
                    {/* Havendo lista identificada, ela substitui a mensagem técnica
                        do ERP — vale para parcial E para erro total (um reenvio que
                        falhou inteiro também tem os recusados nomeados). O texto cru
                        continua no histórico. */}
                    {temPendentes ? (
                      <ul
                        className={`text-[11px] mt-1.5 space-y-1 ${parcial ? 'text-sky-900' : 'text-rose-900'}`}
                      >
                        {e.matriculas_pendentes!.map((pe) => (
                          <li key={pe.matricula}>
                            <span className="font-semibold">{pe.nome || 'Colaborador'}</span>
                            <span className="opacity-70"> — mat {pe.matricula}</span>
                            {pe.motivo && (
                              <span className="block pl-3 opacity-80">{pe.motivo}</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <>
                        {!ok && e.mensagem && (
                          <p
                            className={`text-[11px] mt-1 whitespace-pre-wrap break-words ${
                              parcial
                                ? 'text-sky-800'
                                : pendente
                                  ? 'text-amber-700'
                                  : 'text-rose-700'
                            }`}
                          >
                            {e.mensagem}
                          </p>
                        )}
                        {parcial && (
                          <p className="text-[11px] mt-1 text-sky-800">
                            O ERP não informou os registros recusados — reenvio automático bloqueado
                            (mandaria tudo de novo). Trate pelo TXT ou manualmente.
                          </p>
                        )}
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Conclusão: fiscal notificado automaticamente após os títulos. */}
          {fiscalStatus === 'enviando' && (
            <div className="flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 p-3 text-xs text-sky-800">
              <Loader2 className="h-4 w-4 shrink-0 animate-spin text-sky-500" />
              <span>Títulos criados. Notificando o departamento fiscal…</span>
            </div>
          )}
          {fiscalStatus === 'ok' && (
            <div className="flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">
              <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5 text-emerald-500" />
              <span>
                <strong>Concluído.</strong> Títulos criados e {fiscalMsg}
              </span>
            </div>
          )}
          {fiscalStatus === 'erro' && (
            <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
              <XCircle className="h-4 w-4 shrink-0 mt-0.5 text-rose-500" />
              <span>
                <strong>Títulos criados, mas falha ao notificar o fiscal:</strong> {fiscalMsg}{' '}
                Reenvie ao fiscal pelo botão abaixo.
              </span>
            </div>
          )}

          {/* O reenvio é seletivo: dizer ANTES o que vai ser enviado evita a dúvida
              de "vai mandar tudo de novo?". */}
          {envios.some((e) => (e.matriculas_pendentes?.length ?? 0) > 0) && (
            <p className="text-[11px] text-slate-500">
              O reenvio trata somente{' '}
              <strong>
                {envios.reduce((n, e) => n + (e.matriculas_pendentes?.length ?? 0), 0)} registro(s)
                pendente(s)
              </strong>
              ; os já incluídos na folha não voltam.
            </p>
          )}

          {/* Histórico de tentativas (só quando houve erro/retentativa) */}
          {api.historicoRelevante(tentativas) && (
            <div className="pt-1">
              <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" /> Histórico de tentativas ({tentativas.length})
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
                        <span className="font-semibold text-slate-700">{t.empresa}</span>
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
                            <span className="font-semibold text-emerald-700">enviado</span>
                          )
                        ) : pend ? (
                          <span className="font-semibold text-amber-700">pendente</span>
                        ) : (
                          <span className="font-semibold text-rose-700">erro</span>
                        )}
                        {t.usuario && <span className="text-slate-400">· {t.usuario}</span>}
                      </div>
                      {!ok && !pend && t.mensagem && (
                        <p className="text-[11px] text-rose-600 mt-0.5 whitespace-pre-wrap break-words">
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

        <div className="bg-slate-50 px-5 py-4 border-t border-slate-100 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
          <button
            onClick={() =>
              onClose(resp ? { ...execucao, status: resp.status, envios: resp.envios } : undefined)
            }
            className="py-2.5 px-5 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer"
          >
            {finalizado ? 'Fechar' : 'Depois'}
          </button>
          {/* Só nos processos que notificam: no desconto em folha não há NF para
              enviar ao fiscal, e o endpoint recusaria a chamada. */}
          {notificaFiscal && temEnviado && (
            <button
              onClick={() => dispararFiscal(false)}
              disabled={notificando}
              className="flex items-center justify-center gap-1.5 py-2.5 px-5 border border-brand-200 bg-white hover:bg-brand-50 text-brand-900 rounded-xl text-xs font-bold transition-all cursor-pointer disabled:opacity-60"
            >
              {notificando ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Mail className="h-4 w-4" />
              )}
              {notificando
                ? 'Enviando…'
                : fiscalStatus === 'ok'
                  ? 'Reenviar ao fiscal'
                  : 'Enviar ao fiscal'}
            </button>
          )}
          <button
            onClick={enviar}
            disabled={enviando}
            className="flex items-center justify-center gap-1.5 py-2.5 px-5 bg-brand-900 hover:bg-brand-950 text-white rounded-xl text-xs font-bold shadow-md shadow-brand-950/10 transition-all cursor-pointer disabled:opacity-60"
          >
            {enviando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            {enviando
              ? 'Enviando…'
              : envios.some((e) => e.status === 'parcial')
                ? 'Reenviar pendentes'
                : finalizado
                  ? descontoEmFolha
                    ? 'Relançar'
                    : 'Reenviar'
                  : descontoEmFolha
                    ? 'Lançar na folha'
                    : 'Enviar ao ERP'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
