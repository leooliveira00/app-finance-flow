import { useEffect, useState } from 'react';
import { Save, Plus, Trash2, Percent, Loader2, Briefcase } from 'lucide-react';
import * as api from '../../api';
import { ApiError, CadastroCopart, CadastroCopartFaixa } from '../../api';
import { Toast } from '../../types';

interface Props {
  admin: boolean;
  addToast: (message: string, type: Toast['type']) => void;
}

const FAIXA_VAZIA: CadastroCopartFaixa = {
  nome: '',
  salario_inicial: '0',
  salario_final: '0',
  valores: { consulta: '0', simples: '0', especial: '0' },
};

const TIPOS: Array<keyof CadastroCopartFaixa['valores']> = ['consulta', 'simples', 'especial'];

const inputCls =
  'w-full px-2 py-1.5 bg-white border border-slate-200 rounded-lg text-xs font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:bg-slate-50 disabled:text-slate-400';

export default function CoparticipacaoConfig({ admin, addToast }: Props) {
  const [cadastro, setCadastro] = useState<CadastroCopart | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    api
      .getCadastroCoparticipacao()
      .then(setCadastro)
      .catch((err) =>
        addToast(err instanceof ApiError ? err.message : 'Falha ao carregar o cadastro.', 'error'),
      )
      .finally(() => setCarregando(false));
  }, [addToast]);

  const atualizarFaixa = (i: number, patch: Partial<CadastroCopartFaixa>) => {
    setCadastro((c) =>
      c ? { ...c, faixas: c.faixas.map((f, idx) => (idx === i ? { ...f, ...patch } : f)) } : c,
    );
  };
  const atualizarValor = (i: number, tipo: keyof CadastroCopartFaixa['valores'], valor: string) => {
    setCadastro((c) =>
      c
        ? {
            ...c,
            faixas: c.faixas.map((f, idx) =>
              idx === i ? { ...f, valores: { ...f.valores, [tipo]: valor } } : f,
            ),
          }
        : c,
    );
  };
  const adicionarFaixa = () =>
    setCadastro((c) =>
      c
        ? { ...c, faixas: [...c.faixas, { ...FAIXA_VAZIA, valores: { ...FAIXA_VAZIA.valores } }] }
        : c,
    );
  const removerFaixa = (i: number) =>
    setCadastro((c) => (c ? { ...c, faixas: c.faixas.filter((_, idx) => idx !== i) } : c));

  const salvar = async () => {
    if (!cadastro) return;
    setSalvando(true);
    try {
      const salvo = await api.salvarCadastroCoparticipacao(cadastro);
      setCadastro(salvo);
      addToast('Cadastro salvo.', 'success');
    } catch (err) {
      addToast(err instanceof ApiError ? err.message : 'Falha ao salvar o cadastro.', 'error');
    } finally {
      setSalvando(false);
    }
  };

  if (carregando || !cadastro) {
    return (
      <div className="h-40 flex items-center justify-center text-slate-400">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Coparticipação de plano de saúde</h2>
          <p className="text-xs text-slate-500">
            Faixas salariais, valores por tipo de exame e teto do desconto.
          </p>
        </div>
        {admin && (
          <button
            onClick={salvar}
            disabled={salvando}
            className="flex items-center gap-1.5 py-2 px-4 bg-sky-600 hover:bg-sky-700 text-white rounded-xl text-xs font-bold shadow-lg shadow-sky-600/20 transition-all cursor-pointer disabled:opacity-50 shrink-0"
          >
            {salvando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {salvando ? 'Salvando...' : 'Salvar alterações'}
          </button>
        )}
      </div>

      {/* Parâmetros: teto + salário padrão PJ */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm grid grid-cols-1 sm:grid-cols-2 gap-5">
        <div className="flex items-center gap-3">
          <div className="h-11 w-11 bg-sky-50 border border-sky-100 rounded-xl flex items-center justify-center shrink-0">
            <Percent className="h-5 w-5 text-sky-600" />
          </div>
          <div className="flex-1">
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1">
              Teto do desconto (% do salário)
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              max="100"
              disabled={!admin}
              value={cadastro.teto_percentual}
              onChange={(e) =>
                setCadastro((c) => (c ? { ...c, teto_percentual: e.target.value } : c))
              }
              className={`${inputCls} max-w-[140px]`}
            />
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="h-11 w-11 bg-sky-50 border border-sky-100 rounded-xl flex items-center justify-center shrink-0">
            <Briefcase className="h-5 w-5 text-sky-600" />
          </div>
          <div className="flex-1">
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1">
              Salário padrão PJ (R$)
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              disabled={!admin}
              value={cadastro.salario_padrao_pj}
              onChange={(e) =>
                setCadastro((c) => (c ? { ...c, salario_padrao_pj: e.target.value } : c))
              }
              className={`${inputCls} max-w-[160px]`}
            />
            <p className="text-[10px] text-slate-400 mt-1">
              Usado pelos colaboradores PJ para definir a faixa.
            </p>
          </div>
        </div>
      </div>

      {/* Faixas */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 px-5 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-900">
            Faixas salariais e valores por evento
          </h3>
          {admin && (
            <button
              onClick={adicionarFaixa}
              className="flex items-center gap-1 text-xs font-semibold text-sky-700 hover:text-sky-800 cursor-pointer"
            >
              <Plus className="h-4 w-4" /> Adicionar faixa
            </button>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="bg-slate-50 text-slate-400 font-bold border-b border-slate-100 text-[10px] uppercase tracking-wider">
                <th className="py-3 px-4">Faixa</th>
                <th className="py-3 px-3">Salário inicial</th>
                <th className="py-3 px-3">Salário final</th>
                <th className="py-3 px-3">Consulta</th>
                <th className="py-3 px-3">Exame simples</th>
                <th className="py-3 px-3">Exame especial</th>
                {admin && <th className="py-3 px-3"></th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {cadastro.faixas.map((f, i) => (
                <tr key={i} className="hover:bg-slate-50/40">
                  <td className="py-2 px-4 min-w-[120px]">
                    <input
                      disabled={!admin}
                      value={f.nome}
                      onChange={(e) => atualizarFaixa(i, { nome: e.target.value })}
                      className={inputCls}
                    />
                  </td>
                  <td className="py-2 px-3 min-w-[110px]">
                    <input
                      disabled={!admin}
                      type="number"
                      step="0.01"
                      value={f.salario_inicial}
                      onChange={(e) => atualizarFaixa(i, { salario_inicial: e.target.value })}
                      className={inputCls}
                    />
                  </td>
                  <td className="py-2 px-3 min-w-[110px]">
                    <input
                      disabled={!admin}
                      type="number"
                      step="0.01"
                      value={f.salario_final}
                      onChange={(e) => atualizarFaixa(i, { salario_final: e.target.value })}
                      className={inputCls}
                    />
                  </td>
                  {TIPOS.map((t) => (
                    <td key={t} className="py-2 px-3 min-w-[90px]">
                      <input
                        disabled={!admin}
                        type="number"
                        step="0.01"
                        value={f.valores[t]}
                        onChange={(e) => atualizarValor(i, t, e.target.value)}
                        className={inputCls}
                      />
                    </td>
                  ))}
                  {admin && (
                    <td className="py-2 px-3">
                      <button
                        onClick={() => removerFaixa(i)}
                        className="text-slate-300 hover:text-red-500 transition-colors cursor-pointer"
                        title="Remover faixa"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
              {cadastro.faixas.length === 0 && (
                <tr>
                  <td colSpan={admin ? 7 : 6} className="py-8 text-center text-slate-400">
                    Nenhuma faixa cadastrada.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
