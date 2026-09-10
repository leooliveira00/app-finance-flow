import { useEffect, useState } from 'react';
import { Check, Loader2, Mail } from 'lucide-react';
import * as api from '../../api';
import { ApiError } from '../../api';
import { Toast } from '../../types';

interface Props {
  admin: boolean;
  addToast: (message: string, type: Toast['type']) => void;
}

const inputCls =
  'w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:bg-slate-50 disabled:text-slate-500';

export default function NotificacoesConfig({ admin, addToast }: Props) {
  const [fiscal, setFiscal] = useState('');
  const [copia, setCopia] = useState('');
  const [autoria, setAutoria] = useState('');
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);

  const erro = (err: unknown, fallback: string) =>
    addToast(err instanceof ApiError ? err.message : fallback, 'error');

  const aplicar = (c: api.ConfigNotificacao) => {
    setFiscal(c.fiscal_emails);
    setCopia(c.copia_permanente);
    setAutoria(
      c.atualizado_por && c.atualizado_em
        ? `Alterado por ${c.atualizado_por} em ${new Date(c.atualizado_em).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }).replace(',', '')}`
        : '',
    );
  };

  useEffect(() => {
    api.obterConfigNotificacao()
      .then(aplicar)
      .catch((e) => erro(e, 'Falha ao carregar os destinatários.'))
      .finally(() => setCarregando(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const salvar = async () => {
    setSalvando(true);
    try {
      aplicar(await api.salvarConfigNotificacao(fiscal.trim(), copia.trim()));
      addToast('Destinatários salvos.', 'success');
    } catch (err) {
      erro(err, 'Falha ao salvar os destinatários.');
    } finally {
      setSalvando(false);
    }
  };

  if (carregando) {
    return <div className="h-40 flex items-center justify-center text-slate-400"><Loader2 className="h-6 w-6 animate-spin" /></div>;
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold text-slate-900">Notificações</h2>
        <p className="text-xs text-slate-500">
          Destinatários dos e-mails enviados ao concluir um lançamento. A cópia da{' '}
          <strong>área responsável</strong> não é definida aqui: ela fica no cadastro da área, em
          Setores e permissões, porque a área é dona dos processos.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-3 px-5 border-b border-slate-100 flex items-center gap-2">
          <Mail className="h-4 w-4 text-slate-500" />
          <h3 className="text-sm font-bold text-slate-900">Destinatários institucionais</h3>
        </div>
        <div className="p-5 space-y-4">
          <label className="block">
            <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
              Departamento fiscal
            </span>
            <input
              value={fiscal}
              onChange={(e) => setFiscal(e.target.value)}
              disabled={!admin}
              placeholder="fiscal@financeflow.local"
              className={`mt-1 ${inputCls}`}
            />
            <span className="mt-1 block text-[11px] text-slate-500">
              Recebe a notificação de todos os processos, no campo Para. Separe vários endereços por
              vírgula.
            </span>
          </label>

          <label className="block">
            <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
              Cópia permanente
            </span>
            <input
              value={copia}
              onChange={(e) => setCopia(e.target.value)}
              disabled={!admin}
              placeholder="controladoria@financeflow.local"
              className={`mt-1 ${inputCls}`}
            />
            <span className="mt-1 block text-[11px] text-slate-500">
              Entra em cópia em todos os processos, independente da área. Deixe vazio se não houver.
            </span>
          </label>

          {autoria && <p className="text-[11px] text-slate-400">{autoria}</p>}

          {admin && (
            <div className="flex justify-end">
              <button
                onClick={salvar}
                disabled={salvando}
                className="flex items-center gap-1.5 py-2 px-4 bg-sky-600 hover:bg-sky-700 text-white rounded-xl text-xs font-bold cursor-pointer disabled:opacity-50"
              >
                {salvando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Salvar
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
