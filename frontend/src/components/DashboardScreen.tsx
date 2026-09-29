import { useEffect, useState } from 'react';
import { Play, ClipboardList, Layers, AlertCircle, Loader2, CalendarClock } from 'lucide-react';
import * as api from '../api';
import { Modulo, ApiError } from '../api';
import { Toast } from '../types';

interface DashboardScreenProps {
  onStartExecution: (tipo: string) => void;
  /** Abre o histórico. Com `tipo`, já filtrado naquele rateio (botão do card). */
  onViewHistory: (tipo?: string) => void;
  addToast: (message: string, type: Toast['type']) => void;
}

function dataCurta(iso?: string): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d.toLocaleDateString('pt-BR');
}

export default function DashboardScreen({ onStartExecution, onViewHistory, addToast }: DashboardScreenProps) {
  const [modulos, setModulos] = useState<Modulo[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  // tipo -> criado_em da última execução GRAVADA (para exibir no card).
  const [ultimaPorTipo, setUltimaPorTipo] = useState<Record<string, string>>({});

  useEffect(() => {
    let ativo = true;
    // Execuções são um extra do card: uma falha ali não deve derrubar os módulos.
    Promise.allSettled([api.getModulos(), api.listarExecucoes()])
      .then(([mods, execs]) => {
        if (!ativo) return;
        if (mods.status === 'fulfilled') {
          setModulos(mods.value);
        } else {
          const msg = mods.reason instanceof ApiError ? mods.reason.message : 'Falha ao carregar os rateios.';
          setErro(msg);
          addToast(msg, 'error');
        }
        if (execs.status === 'fulfilled') {
          // A lista vem ordenada por criado_em desc -> 1ª ocorrência de cada tipo é a mais recente.
          const mapa: Record<string, string> = {};
          for (const ex of execs.value) {
            if (ex.criado_em && !mapa[ex.tipo]) mapa[ex.tipo] = ex.criado_em;
          }
          setUltimaPorTipo(mapa);
        }
      })
      .finally(() => ativo && setLoading(false));
    return () => {
      ativo = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-8 animate-fade-in">
      <div className="bg-gradient-to-r from-brand-950 to-brand-900 rounded-3xl p-8 text-white shadow-lg relative overflow-hidden border border-brand-900">
        <div className="absolute top-0 right-0 w-80 h-80 bg-brand-800 rounded-full mix-blend-multiply filter blur-3xl opacity-25 translate-x-1/3 -translate-y-1/3" />
        <div className="relative z-10 max-w-2xl">
          <h1 className="text-3xl font-bold tracking-tight">Painel de rateios</h1>
          <p className="mt-1 text-sm text-brand-200">Selecione um rateio da sua área para iniciar uma execução.</p>
        </div>
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Rateios disponíveis</h2>
          </div>
          {!loading && !erro && (
            <span className="text-xs font-semibold bg-slate-100 text-slate-600 px-3 py-1 rounded-full">
              {modulos.length} {modulos.length === 1 ? 'rateio' : 'rateios'}
            </span>
          )}
        </div>

        {loading && (
          <div className="flex items-center justify-center py-16 text-slate-400">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        )}

        {erro && !loading && (
          <div className="bg-rose-50 border border-rose-200 rounded-2xl p-5 flex items-center gap-3 text-rose-800">
            <AlertCircle className="h-5 w-5 text-rose-500 shrink-0" />
            <span className="text-sm font-medium">{erro}</span>
          </div>
        )}

        {!loading && !erro && modulos.length === 0 && (
          <div className="bg-slate-50 border border-slate-200 rounded-2xl p-8 text-center text-sm text-slate-500">
            Nenhum rateio disponível para as suas áreas.
          </div>
        )}

        {!loading && !erro && modulos.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {modulos.map((modulo) => (
              <div
                key={modulo.tipo}
                id={`card-${modulo.tipo}`}
                className="bg-white rounded-2xl border border-slate-200/80 shadow-sm hover:shadow-md transition-all flex flex-col justify-between overflow-hidden"
              >
                <div className="p-6">
                  {/* Área ABAIXO do nome, alinhada à esquerda: o nome da área é
                      livre (até 60 caracteres) e, na mesma linha do título, os dois
                      disputavam a largura do cartão — um nome longo ("Tecnologia da
                      Informação") comprimia o título. Em linhas separadas cada um
                      usa a largura inteira, e o badge só trunca no caso extremo. */}
                  <div className="mb-4 space-y-2">
                    <h3 className="text-base font-bold text-slate-900 tracking-tight leading-snug">
                      {modulo.nome}
                    </h3>
                    {modulo.area && (
                      <span
                        title={modulo.area}
                        className="inline-flex max-w-full items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-brand-50 text-brand-700 border border-brand-200"
                      >
                        <Layers className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">{modulo.area}</span>
                      </span>
                    )}
                  </div>
                  <p title={modulo.descricao} className="text-xs text-slate-500 leading-relaxed mb-3 line-clamp-2">{modulo.descricao}</p>
                  <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
                    <CalendarClock className="h-3.5 w-3.5 shrink-0" />
                    {ultimaPorTipo[modulo.tipo] ? (
                      <span title={new Date(ultimaPorTipo[modulo.tipo]).toLocaleString('pt-BR')}>
                        Última execução:{' '}
                        <strong className="font-semibold text-slate-600">{dataCurta(ultimaPorTipo[modulo.tipo])}</strong>
                      </span>
                    ) : (
                      <span>Sem execuções gravadas</span>
                    )}
                  </div>
                </div>

                <div className="px-6 py-4 bg-slate-50/50 border-t border-slate-100 flex gap-2.5">
                  <button
                    id={`btn-new-${modulo.tipo}`}
                    onClick={() => onStartExecution(modulo.tipo)}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3.5 rounded-xl text-xs font-bold transition-all cursor-pointer shadow-sm bg-brand-900 text-white hover:bg-brand-950 border border-transparent"
                  >
                    <Play className="h-3.5 w-3.5 fill-current" />
                    Nova execução
                  </button>
                  <button
                    id={`btn-hist-${modulo.tipo}`}
                    onClick={() => onViewHistory(modulo.tipo)}
                    className="flex items-center justify-center gap-1.5 py-2 px-3.5 rounded-xl text-xs font-semibold text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 transition-colors cursor-pointer"
                  >
                    <ClipboardList className="h-3.5 w-3.5 text-slate-500" />
                    Histórico
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
