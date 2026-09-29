import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Plus, Trash2, Loader2, Pencil, X, Check, Building2 } from 'lucide-react';
import * as api from '../../api';
import { ApiError, Empresa, EmpresaInput } from '../../api';
import { Toast } from '../../types';
import Dropdown from '../Dropdown';

interface Props {
  admin: boolean;
  addToast: (message: string, type: Toast['type']) => void;
}

const inputCls =
  'w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500';

const VAZIO: EmpresaInput = {
  nome: '',
  rest: '',
  cnpj: '',
  rotina_erp: 'ae',
  prenota_produto: '',
  prenota_filial: '',
};

export default function EmpresasConfig({ admin, addToast }: Props) {
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [modalAberto, setModalAberto] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<EmpresaInput>(VAZIO);

  const erro = (err: unknown, fallback: string) =>
    addToast(err instanceof ApiError ? err.message : fallback, 'error');
  const recarregar = () =>
    api
      .listarEmpresas()
      .then(setEmpresas)
      .catch((e) => erro(e, 'Falha ao carregar empresas.'));

  useEffect(() => {
    api
      .listarEmpresas()
      .then(setEmpresas)
      .catch((e) => erro(e, 'Falha ao carregar empresas.'))
      .finally(() => setCarregando(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (campo: keyof EmpresaInput, v: string) => setForm((f) => ({ ...f, [campo]: v }));
  const abrirNovo = () => {
    setEditId(null);
    setForm(VAZIO);
    setModalAberto(true);
  };
  const abrirEdicao = (e: Empresa) => {
    setEditId(e.id);
    setForm({
      nome: e.nome,
      rest: e.rest,
      cnpj: e.cnpj,
      rotina_erp: e.rotina_erp,
      prenota_produto: e.prenota_produto,
      prenota_filial: e.prenota_filial,
    });
    setModalAberto(true);
  };
  const fechar = () => {
    if (!salvando) setModalAberto(false);
  };

  const salvar = async () => {
    if (!form.nome.trim()) {
      addToast('Informe o nome da empresa.', 'warning');
      return;
    }
    setSalvando(true);
    try {
      await api.salvarEmpresa(form, editId ?? undefined);
      setModalAberto(false);
      await recarregar();
      addToast('Empresa salva.', 'success');
    } catch (err) {
      erro(err, 'Falha ao salvar.');
    } finally {
      setSalvando(false);
    }
  };
  const remover = async (e: Empresa) => {
    try {
      await api.removerEmpresa(e.id);
      await recarregar();
      addToast('Empresa removida.', 'success');
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
          <h2 className="text-lg font-bold text-slate-900">Empresas do grupo</h2>
          <p className="text-xs text-slate-500">
            Fonte única do rateio de pagamento: o <strong>rest</strong> do Protheus, o{' '}
            <strong>CNPJ</strong> (reconciliação da NF/boleto) e a <strong>rotina</strong> de
            lançamento no ERP. A detecção por CNPJ vale no próximo restart do backend.
          </p>
        </div>
        {admin && (
          <button
            onClick={abrirNovo}
            className="flex items-center gap-1.5 py-2 px-4 bg-sky-600 hover:bg-sky-700 text-white rounded-xl text-xs font-bold shadow-lg shadow-sky-600/20 transition-all cursor-pointer shrink-0"
          >
            <Plus className="h-4 w-4" /> Nova empresa
          </button>
        )}
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-3 px-5 border-b border-slate-100 flex items-center gap-2">
          <Building2 className="h-4 w-4 text-slate-500" />
          <h3 className="text-sm font-bold text-slate-900">Empresas</h3>
          <span className="text-[11px] font-semibold bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
            {empresas.length}
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50">
              <tr className="text-slate-400 font-bold border-b border-slate-100 text-[10px] uppercase tracking-wider">
                <th className="py-3 px-5">Nome</th>
                <th className="py-3 px-4">Rest</th>
                <th className="py-3 px-4">CNPJ</th>
                <th className="py-3 px-4">Rotina</th>
                {admin && <th className="py-3 px-4 w-20"></th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {empresas.map((e) => (
                <tr key={e.id} className="hover:bg-slate-50/50">
                  <td className="py-2.5 px-5 font-medium text-slate-800">{e.nome}</td>
                  <td className="py-2.5 px-4 font-mono text-slate-500">{e.rest || '—'}</td>
                  <td className="py-2.5 px-4 font-mono text-slate-500">{e.cnpj || '—'}</td>
                  <td className="py-2.5 px-4">
                    {e.rotina_erp === 'pre_nota' ? 'Pré-nota' : 'Aut. de Entrega'}
                  </td>
                  {admin && (
                    <td className="py-2.5 px-4">
                      <div className="flex gap-1">
                        <button
                          onClick={() => abrirEdicao(e)}
                          className="p-1.5 text-slate-400 hover:text-sky-600 hover:bg-slate-50 rounded-lg cursor-pointer"
                          title="Editar"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => remover(e)}
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
              {empresas.length === 0 && (
                <tr>
                  <td colSpan={admin ? 5 : 4} className="py-8 text-center text-slate-400">
                    Nenhuma empresa cadastrada.
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
              className="bg-white rounded-2xl shadow-xl max-w-xl w-full my-8"
              onClick={(ev) => ev.stopPropagation()}
            >
              <div className="flex items-center justify-between p-5 border-b border-slate-100">
                <h3 className="text-sm font-bold text-slate-900">
                  {editId === null ? 'Nova empresa' : 'Editar empresa'}
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
                  Nome
                  <input
                    value={form.nome}
                    onChange={(e) => set('nome', e.target.value)}
                    placeholder="Vertex"
                    className={inputCls}
                  />
                </label>
                <label className="text-[11px] font-semibold text-slate-500">
                  Rest (Protheus)
                  <input
                    value={form.rest}
                    onChange={(e) => set('rest', e.target.value)}
                    placeholder="rest02"
                    className={`${inputCls} font-mono`}
                  />
                </label>
                <label className="text-[11px] font-semibold text-slate-500">
                  CNPJ
                  <input
                    value={form.cnpj}
                    onChange={(e) => set('cnpj', e.target.value)}
                    placeholder="23.456.780/0001-84"
                    className={`${inputCls} font-mono`}
                  />
                </label>
                <label className="text-[11px] font-semibold text-slate-500">
                  Rotina ERP
                  <div className="mt-1">
                    <Dropdown
                      value={form.rotina_erp}
                      onChange={(v) => set('rotina_erp', v)}
                      className="w-full"
                      opcoes={[
                        { value: 'ae', label: 'Aut. de Entrega' },
                        { value: 'pre_nota', label: 'Pré-nota' },
                      ]}
                    />
                  </div>
                </label>
                {form.rotina_erp === 'pre_nota' && (
                  <>
                    <label className="text-[11px] font-semibold text-slate-500">
                      Produto (pré-nota)
                      <input
                        value={form.prenota_produto}
                        onChange={(e) => set('prenota_produto', e.target.value)}
                        placeholder="400366"
                        className={`${inputCls} font-mono`}
                      />
                    </label>
                    <label className="text-[11px] font-semibold text-slate-500">
                      Filial (pré-nota)
                      <input
                        value={form.prenota_filial}
                        onChange={(e) => set('prenota_filial', e.target.value)}
                        placeholder="01"
                        className={`${inputCls} font-mono`}
                      />
                    </label>
                  </>
                )}
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
