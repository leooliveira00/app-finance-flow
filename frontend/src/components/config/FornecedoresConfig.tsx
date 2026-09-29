import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Plus, Trash2, Loader2, Pencil, X, Check, Truck } from 'lucide-react';
import * as api from '../../api';
import { ApiError, Fornecedor, FornecedorInput } from '../../api';
import { Toast } from '../../types';

interface Props {
  admin: boolean;
  addToast: (message: string, type: Toast['type']) => void;
}

const inputCls =
  'w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500';

const VAZIO: FornecedorInput = { nome: '', cnpj: '' };

export default function FornecedoresConfig({ admin, addToast }: Props) {
  const [fornecedores, setFornecedores] = useState<Fornecedor[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [modalAberto, setModalAberto] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<FornecedorInput>(VAZIO);

  const erro = (err: unknown, fallback: string) =>
    addToast(err instanceof ApiError ? err.message : fallback, 'error');
  const recarregar = () =>
    api
      .listarFornecedores()
      .then(setFornecedores)
      .catch((e) => erro(e, 'Falha ao carregar fornecedores.'));

  useEffect(() => {
    api
      .listarFornecedores()
      .then(setFornecedores)
      .catch((e) => erro(e, 'Falha ao carregar fornecedores.'))
      .finally(() => setCarregando(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (campo: keyof FornecedorInput, v: string) => setForm((f) => ({ ...f, [campo]: v }));
  const abrirNovo = () => {
    setEditId(null);
    setForm(VAZIO);
    setModalAberto(true);
  };
  const abrirEdicao = (f: Fornecedor) => {
    setEditId(f.id);
    setForm({ nome: f.nome, cnpj: f.cnpj });
    setModalAberto(true);
  };
  const fechar = () => {
    if (!salvando) setModalAberto(false);
  };

  const salvar = async () => {
    if (!form.nome.trim()) {
      addToast('Informe o nome do fornecedor.', 'warning');
      return;
    }
    setSalvando(true);
    try {
      await api.salvarFornecedor(form, editId ?? undefined);
      setModalAberto(false);
      await recarregar();
      addToast('Fornecedor salvo.', 'success');
    } catch (err) {
      erro(err, 'Falha ao salvar.');
    } finally {
      setSalvando(false);
    }
  };
  const remover = async (f: Fornecedor) => {
    try {
      await api.removerFornecedor(f.id);
      await recarregar();
      addToast('Fornecedor removido.', 'success');
    } catch (err) {
      erro(err, 'Falha ao remover.');
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
          <h2 className="text-lg font-bold text-slate-900">Fornecedores</h2>
          <p className="text-xs text-slate-500">
            Quem recebe o título no ERP: operadoras de plano de saúde e prestadores de outras
            naturezas, como a telefonia. O <strong>nome</strong> identifica o fornecedor no rateio e
            o <strong>CNPJ</strong> é usado no lançamento ao ERP (só os dígitos) e na reconciliação
            da NF/boleto, para separar prestador de tomador.
          </p>
        </div>
        {admin && (
          <button
            onClick={abrirNovo}
            className="flex items-center gap-1.5 py-2 px-4 bg-sky-600 hover:bg-sky-700 text-white rounded-xl text-xs font-bold shadow-lg shadow-sky-600/20 transition-all cursor-pointer shrink-0"
          >
            <Plus className="h-4 w-4" /> Novo fornecedor
          </button>
        )}
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-3 px-5 border-b border-slate-100 flex items-center gap-2">
          <Truck className="h-4 w-4 text-slate-500" />
          <h3 className="text-sm font-bold text-slate-900">Cadastrados</h3>
          <span className="text-[11px] font-semibold bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
            {fornecedores.length}
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50">
              <tr className="text-slate-400 font-bold border-b border-slate-100 text-[10px] uppercase tracking-wider">
                <th className="py-3 px-5">Nome</th>
                <th className="py-3 px-4">CNPJ</th>
                {admin && <th className="py-3 px-4 w-20"></th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {fornecedores.map((f) => (
                <tr key={f.id} className="hover:bg-slate-50/50">
                  <td className="py-2.5 px-5 font-medium text-slate-800 capitalize">{f.nome}</td>
                  <td className="py-2.5 px-4 font-mono text-slate-500">{f.cnpj || '—'}</td>
                  {admin && (
                    <td className="py-2.5 px-4">
                      <div className="flex gap-1">
                        <button
                          onClick={() => abrirEdicao(f)}
                          className="p-1.5 text-slate-400 hover:text-sky-600 hover:bg-slate-50 rounded-lg cursor-pointer"
                          title="Editar"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => remover(f)}
                          className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-slate-50 rounded-lg cursor-pointer"
                          title="Remover"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
              {fornecedores.length === 0 && (
                <tr>
                  <td colSpan={admin ? 3 : 2} className="py-8 text-center text-slate-400">
                    Nenhum fornecedor cadastrado.
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
              className="bg-white rounded-2xl shadow-xl max-w-md w-full my-8"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between p-5 border-b border-slate-100">
                <h3 className="text-sm font-bold text-slate-900">
                  {editId === null ? 'Novo fornecedor' : 'Editar fornecedor'}
                </h3>
                <button
                  onClick={fechar}
                  className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 cursor-pointer"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="p-5 space-y-3">
                <label className="block text-[11px] font-semibold text-slate-500">
                  Nome
                  <input
                    value={form.nome}
                    onChange={(e) => set('nome', e.target.value)}
                    placeholder="unimed"
                    className={inputCls}
                  />
                </label>
                <label className="block text-[11px] font-semibold text-slate-500">
                  CNPJ
                  <input
                    value={form.cnpj}
                    onChange={(e) => set('cnpj', e.target.value)}
                    placeholder="45.678.910/0001-66"
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
                  {editId === null ? 'Criar' : 'Salvar'}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
