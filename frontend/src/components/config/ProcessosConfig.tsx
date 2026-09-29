import { useEffect, useState } from 'react';
import { Loader2, Power, Workflow } from 'lucide-react';
import * as api from '../../api';
import { ApiError, ProcessoStatus } from '../../api';
import { Toast } from '../../types';

interface Props {
  addToast: (message: string, type: Toast['type']) => void;
}

function dataHora(iso: string | null): string {
  if (!iso) return '';
  return new Date(iso)
    .toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
    .replace(',', '');
}

export default function ProcessosConfig({ addToast }: Props) {
  const [processos, setProcessos] = useState<ProcessoStatus[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [alterando, setAlterando] = useState<string | null>(null);

  const erro = (err: unknown, fallback: string) =>
    addToast(err instanceof ApiError ? err.message : fallback, 'error');

  useEffect(() => {
    api
      .listarProcessos()
      .then(setProcessos)
      .catch((e) => erro(e, 'Falha ao carregar os processos.'))
      .finally(() => setCarregando(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const alternar = async (p: ProcessoStatus) => {
    setAlterando(p.tipo);
    try {
      await api.definirProcessoAtivo(p.tipo, !p.ativo);
      setProcessos(await api.listarProcessos());
      addToast(
        p.ativo
          ? `${p.nome} foi desativado e não aceita novas execuções.`
          : `${p.nome} foi ativado e voltou ao painel.`,
        'success',
      );
    } catch (err) {
      erro(err, 'Falha ao alterar a disponibilidade do processo.');
    } finally {
      setAlterando(null);
    }
  };

  if (carregando) {
    return (
      <div className="h-40 flex items-center justify-center text-slate-400">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold text-slate-900">Processos</h2>
        <p className="text-xs text-slate-500">
          Disponibilidade de cada processo na ferramenta. O processo <strong>inativo</strong> sai do
          painel e não aceita novas execuções. O histórico dele continua disponível para consulta,
          as execuções já gravadas podem ser concluídas e os cadastros seguem acessíveis aqui, para
          completar o que falta antes de reativá-lo.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-3 px-5 border-b border-slate-100 flex items-center gap-2">
          <Workflow className="h-4 w-4 text-slate-500" />
          <h3 className="text-sm font-bold text-slate-900">Cadastrados</h3>
          <span className="text-[11px] font-semibold bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
            {processos.length}
          </span>
        </div>
        <ul className="divide-y divide-slate-100">
          {processos.map((p) => (
            <li key={p.tipo} className="flex items-start gap-4 px-5 py-3.5">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-semibold text-slate-800">{p.nome}</span>
                  {p.area && (
                    <span className="text-[11px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
                      {p.area}
                    </span>
                  )}
                  {!p.ativo && (
                    <span className="text-[11px] font-bold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
                      Inativo
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-0.5">{p.descricao}</p>
                {p.atualizado_por && (
                  <p className="text-[11px] text-slate-400 mt-1">
                    {p.ativo ? 'Ativado' : 'Desativado'} por {p.atualizado_por} em{' '}
                    {dataHora(p.atualizado_em)}
                  </p>
                )}
              </div>
              <button
                onClick={() => alternar(p)}
                disabled={alterando === p.tipo}
                className={`shrink-0 inline-flex items-center gap-1.5 py-2 px-3.5 rounded-xl text-xs font-bold border transition-colors cursor-pointer disabled:opacity-50 ${
                  p.ativo
                    ? 'border-slate-200 text-slate-600 hover:bg-slate-50'
                    : 'border-transparent bg-brand-900 text-white hover:bg-brand-950'
                }`}
              >
                {alterando === p.tipo ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Power className="h-3.5 w-3.5" />
                )}
                {p.ativo ? 'Desativar' : 'Ativar'}
              </button>
            </li>
          ))}
          {processos.length === 0 && (
            <li className="py-8 text-center text-slate-400 text-xs">Nenhum processo descoberto.</li>
          )}
        </ul>
      </div>
    </div>
  );
}
