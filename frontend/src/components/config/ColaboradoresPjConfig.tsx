import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Plus, Trash2, Loader2, Briefcase, Pencil, Check, X } from 'lucide-react';
import * as api from '../../api';
import { ApiError, ColaboradorPJ } from '../../api';
import { Toast } from '../../types';

interface Props {
  admin: boolean;
  addToast: (message: string, type: Toast['type']) => void;
}

const inputCls =
  'w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:bg-slate-50 disabled:text-slate-400';

/**
 * Cadastro de Colaboradores PJ — dado-mestre COMPARTILHADO entre rateios:
 * a coparticipação usa o salário padrão (para a faixa) e o pagamento usa a
 * alocação contábil (centro de custo / empresa / classe de valor).
 */
export default function ColaboradoresPjConfig({ admin, addToast }: Props) {
  const [pjs, setPjs] = useState<ColaboradorPJ[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [modalAberto, setModalAberto] = useState(false);
  const [editando, setEditando] = useState(false); // true = editar (CPF travado)
  const [fCpf, setFCpf] = useState('');
  const [fNome, setFNome] = useState('');
  const [fCc, setFCc] = useState('');
  const [fEmpresa, setFEmpresa] = useState('');
  const [fClasse, setFClasse] = useState('');

  const erro = (err: unknown, fallback: string) =>
    addToast(err instanceof ApiError ? err.message : fallback, 'error');
  const recarregar = () =>
    api
      .listarPJ()
      .then(setPjs)
      .catch(() => undefined);

  useEffect(() => {
    api
      .listarPJ()
      .then(setPjs)
      .catch(() => undefined)
      .finally(() => setCarregando(false));
  }, []);

  const abrirNovo = () => {
    setEditando(false);
    setFCpf('');
    setFNome('');
    setFCc('');
    setFEmpresa('');
    setFClasse('');
    setModalAberto(true);
  };
  const abrirEdicao = (p: ColaboradorPJ) => {
    setEditando(true);
    setFCpf(p.cpf);
    setFNome(p.nome || '');
    setFCc(p.centro_custo || '');
    setFEmpresa(p.empresa || '');
    setFClasse(p.classe_valor || '');
    setModalAberto(true);
  };
  const fechar = () => {
    if (!salvando) setModalAberto(false);
  };

  const salvar = async () => {
    if (!fCpf.trim()) {
      addToast('Informe o CPF.', 'warning');
      return;
    }
    setSalvando(true);
    try {
      await api.adicionarPJ(fCpf.trim(), fNome.trim(), {
        centro_custo: fCc.trim(),
        empresa: fEmpresa.trim(),
        classe_valor: fClasse.trim(),
      });
      setModalAberto(false);
      await recarregar();
      addToast(editando ? 'Colaborador PJ atualizado.' : 'Colaborador PJ adicionado.', 'success');
    } catch (err) {
      erro(err, 'Falha ao salvar o PJ.');
    } finally {
      setSalvando(false);
    }
  };
  const remover = async (cpf: string) => {
    try {
      await api.removerPJ(cpf);
      await recarregar();
      addToast('Colaborador PJ removido.', 'success');
    } catch (err) {
      erro(err, 'Falha ao remover PJ.');
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
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Colaboradores PJ</h2>
          <p className="text-xs text-slate-500">
            Cadastro compartilhado entre rateios. Na <strong>coparticipação</strong>, o PJ usa o
            salário padrão para a faixa; no <strong>pagamento</strong>, usa a alocação (centro de
            custo, empresa e classe de valor). Sem classe de valor, o lançamento no ERP é recusado.
          </p>
        </div>
        {admin && (
          <button
            onClick={abrirNovo}
            className="flex items-center gap-1.5 py-2 px-4 bg-sky-600 hover:bg-sky-700 text-white rounded-xl text-xs font-bold shadow-lg shadow-sky-600/20 transition-all cursor-pointer shrink-0"
          >
            <Plus className="h-4 w-4" /> Novo PJ
          </button>
        )}
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-3 px-5 border-b border-slate-100 flex items-center gap-2">
          <Briefcase className="h-4 w-4 text-slate-500" />
          <h3 className="text-sm font-bold text-slate-900">Colaboradores PJ</h3>
          <span className="text-[11px] font-semibold bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
            {pjs.length}
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50">
              <tr className="text-[10px] font-bold text-slate-400 uppercase tracking-wide border-b border-slate-100">
                <th className="py-3 px-5">CPF</th>
                <th className="py-3 px-4">Nome</th>
                <th className="py-3 px-4">Centro de custo</th>
                <th className="py-3 px-4">Empresa</th>
                <th className="py-3 px-4">Classe de valor</th>
                {admin && <th className="py-3 px-4 w-20" />}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {pjs.map((p) => (
                <tr key={p.cpf} className="hover:bg-slate-50/50">
                  <td className="py-2.5 px-5 font-mono text-slate-500">{p.cpf}</td>
                  <td className="py-2.5 px-4 text-slate-700">{p.nome || '—'}</td>
                  <td className="py-2.5 px-4 text-slate-500 font-mono">{p.centro_custo || '—'}</td>
                  <td className="py-2.5 px-4 text-slate-500">{p.empresa || '—'}</td>
                  <td
                    className={`py-2.5 px-4 font-mono ${p.classe_valor ? 'text-slate-500' : 'text-amber-600 font-semibold'}`}
                  >
                    {p.classe_valor || 'em branco'}
                  </td>
                  {admin && (
                    <td className="py-2.5 px-4">
                      <div className="flex gap-1">
                        <button
                          onClick={() => abrirEdicao(p)}
                          className="p-1.5 text-slate-400 hover:text-sky-600 hover:bg-slate-50 rounded-lg cursor-pointer"
                          title="Editar alocação"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => remover(p.cpf)}
                          className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-slate-50 rounded-lg cursor-pointer"
                          title="Remover do PJ"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
              {pjs.length === 0 && (
                <tr>
                  <td colSpan={admin ? 6 : 5} className="py-8 text-center text-slate-400">
                    Nenhum colaborador PJ cadastrado.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {modalAberto &&
        createPortal(
          <div
            className="fixed inset-0 z-40 bg-slate-900/40 flex items-start justify-center p-4 overflow-y-auto"
            onClick={fechar}
          >
            <div
              className="bg-white rounded-2xl shadow-xl max-w-lg w-full my-8"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between p-5 border-b border-slate-100">
                <h3 className="text-sm font-bold text-slate-900">
                  {editando ? 'Editar colaborador PJ' : 'Novo colaborador PJ'}
                </h3>
                <button
                  onClick={fechar}
                  className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 cursor-pointer"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="p-5 grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label className="text-[11px] font-semibold text-slate-500">
                  CPF
                  <input
                    value={fCpf}
                    onChange={(e) => setFCpf(e.target.value)}
                    disabled={editando}
                    placeholder="000.000.000-00"
                    className={`${inputCls} font-mono`}
                  />
                </label>
                <label className="text-[11px] font-semibold text-slate-500">
                  Nome
                  <input
                    value={fNome}
                    onChange={(e) => setFNome(e.target.value)}
                    placeholder="Nome do colaborador"
                    className={inputCls}
                  />
                </label>
                <label className="text-[11px] font-semibold text-slate-500">
                  Centro de custo
                  <input
                    value={fCc}
                    onChange={(e) => setFCc(e.target.value)}
                    placeholder="ex.: 401070101"
                    className={`${inputCls} font-mono`}
                  />
                </label>
                <label className="text-[11px] font-semibold text-slate-500">
                  Empresa
                  <input
                    value={fEmpresa}
                    onChange={(e) => setFEmpresa(e.target.value)}
                    placeholder="ex.: Vertex"
                    className={inputCls}
                  />
                </label>
                <label className="text-[11px] font-semibold text-slate-500 sm:col-span-2">
                  Classe de valor
                  <input
                    value={fClasse}
                    onChange={(e) => setFClasse(e.target.value)}
                    placeholder="ex.: 000123"
                    className={`${inputCls} font-mono`}
                  />
                </label>
              </div>
              <div className="flex justify-end gap-2 p-5 border-t border-slate-100">
                <button
                  onClick={fechar}
                  disabled={salvando}
                  className="py-2 px-4 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 cursor-pointer disabled:opacity-50"
                >
                  Cancelar
                </button>
                <button
                  onClick={salvar}
                  disabled={salvando}
                  className="flex items-center gap-1.5 py-2 px-4 bg-sky-600 hover:bg-sky-700 text-white rounded-xl text-xs font-bold cursor-pointer disabled:opacity-50"
                >
                  {salvando ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Check className="h-4 w-4" />
                  )}{' '}
                  {editando ? 'Salvar' : 'Adicionar'}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
