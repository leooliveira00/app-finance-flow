import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { Plus, Trash2, Loader2, Pencil, X, Check, Search, Building2 } from 'lucide-react';
import * as api from '../../api';
import { ApiError, CentroCusto } from '../../api';
import { Toast } from '../../types';

interface Props {
  admin: boolean;
  addToast: (message: string, type: Toast['type']) => void;
}

const inputCls =
  'w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500';

export default function CentroCustoConfig({ admin, addToast }: Props) {
  const [centros, setCentros] = useState<CentroCusto[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [busca, setBusca] = useState('');

  const [modalAberto, setModalAberto] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [fCodigo, setFCodigo] = useState('');
  const [fNome, setFNome] = useState('');
  const [salvando, setSalvando] = useState(false);

  const erro = (err: unknown, fallback: string) =>
    addToast(err instanceof ApiError ? err.message : fallback, 'error');
  const recarregar = () => api.listarCentrosCusto().then(setCentros).catch((e) => erro(e, 'Falha ao carregar centros de custo.'));

  useEffect(() => {
    api.listarCentrosCusto().then(setCentros).catch((e) => erro(e, 'Falha ao carregar centros de custo.')).finally(() => setCarregando(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const filtrados = useMemo(() => {
    const q = busca.trim().toLowerCase();
    if (!q) return centros;
    return centros.filter((c) => c.codigo.toLowerCase().includes(q) || c.nome.toLowerCase().includes(q));
  }, [centros, busca]);

  const abrirNovo = () => { setEditId(null); setFCodigo(''); setFNome(''); setModalAberto(true); };
  const abrirEdicao = (c: CentroCusto) => { setEditId(c.id); setFCodigo(c.codigo); setFNome(c.nome); setModalAberto(true); };
  const fechar = () => { if (!salvando) setModalAberto(false); };

  const salvar = async () => {
    if (!fCodigo.trim() || !fNome.trim()) { addToast('Informe código e nome.', 'warning'); return; }
    setSalvando(true);
    try {
      if (editId === null) await api.criarCentroCusto(fCodigo.trim(), fNome.trim());
      else await api.atualizarCentroCusto(editId, fCodigo.trim(), fNome.trim());
      setModalAberto(false);
      await recarregar();
      addToast('Centro de custo salvo.', 'success');
    } catch (err) { erro(err, 'Falha ao salvar.'); } finally { setSalvando(false); }
  };
  const remover = async (c: CentroCusto) => {
    try { await api.removerCentroCusto(c.id); await recarregar(); addToast('Centro de custo removido.', 'success'); }
    catch (err) { erro(err, 'Falha ao remover.'); }
  };

  if (carregando) {
    return <div className="h-40 flex items-center justify-center text-slate-400"><Loader2 className="h-6 w-6 animate-spin" /></div>;
  }

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Centros de custo</h2>
          <p className="text-xs text-slate-500">
            Dicionário código → nome, para exibir o nome amigável nos resultados e ao atribuir um PJ a um centro de custo.
            Não é fonte contábil: o centro de custo do colaborador comum vem sempre da API.
          </p>
        </div>
        {admin && (
          <button onClick={abrirNovo} className="flex items-center gap-1.5 py-2 px-4 bg-sky-600 hover:bg-sky-700 text-white rounded-xl text-xs font-bold shadow-lg shadow-sky-600/20 transition-all cursor-pointer shrink-0">
            <Plus className="h-4 w-4" /> Novo centro
          </button>
        )}
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-3 px-5 border-b border-slate-100 flex items-center gap-2">
          <Building2 className="h-4 w-4 text-slate-500" />
          <h3 className="text-sm font-bold text-slate-900">Cadastrados</h3>
          <span className="text-[11px] font-semibold bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">{centros.length}</span>
          <div className="ml-auto relative">
            <Search className="h-3.5 w-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar…" className="pl-8 pr-2.5 py-1.5 bg-white border border-slate-200 rounded-lg text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500 w-40" />
          </div>
        </div>
        <div className="overflow-x-auto max-h-[520px] overflow-y-auto">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-slate-50">
              <tr className="text-slate-400 font-bold border-b border-slate-100 text-[10px] uppercase tracking-wider">
                <th className="py-3 px-5">Código</th>
                <th className="py-3 px-4">Nome</th>
                {admin && <th className="py-3 px-4 w-20"></th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {filtrados.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50/50">
                  <td className="py-2.5 px-5 font-mono text-slate-500">{c.codigo}</td>
                  <td className="py-2.5 px-4 font-medium text-slate-800">{c.nome || '—'}</td>
                  {admin && (
                    <td className="py-2.5 px-4">
                      <div className="flex gap-1">
                        <button onClick={() => abrirEdicao(c)} className="p-1.5 text-slate-400 hover:text-sky-600 hover:bg-slate-50 rounded-lg cursor-pointer" title="Editar"><Pencil className="h-4 w-4" /></button>
                        <button onClick={() => remover(c)} className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-slate-50 rounded-lg cursor-pointer" title="Remover"><Trash2 className="h-4 w-4" /></button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
              {filtrados.length === 0 && (
                <tr><td colSpan={admin ? 3 : 2} className="py-8 text-center text-slate-400">Nenhum centro de custo encontrado.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {modalAberto && createPortal(
        <div className="fixed inset-0 z-40 bg-slate-900/40 flex items-start justify-center p-4 overflow-y-auto" onClick={fechar}>
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full my-8" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-5 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900">{editId === null ? 'Novo centro de custo' : 'Editar centro de custo'}</h3>
              <button onClick={fechar} className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 cursor-pointer"><X className="h-4 w-4" /></button>
            </div>
            <div className="p-5 space-y-3">
              <label className="block text-[11px] font-semibold text-slate-500">Código
                <input value={fCodigo} onChange={(e) => setFCodigo(e.target.value)} placeholder="401070101" className={`${inputCls} font-mono`} />
              </label>
              <label className="block text-[11px] font-semibold text-slate-500">Nome
                <input value={fNome} onChange={(e) => setFNome(e.target.value)} placeholder="Nome do centro de custo" className={inputCls} />
              </label>
            </div>
            <div className="flex justify-end gap-2 p-5 border-t border-slate-100">
              <button onClick={fechar} disabled={salvando} className="py-2 px-4 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 cursor-pointer disabled:opacity-50">Cancelar</button>
              <button onClick={salvar} disabled={salvando} className="flex items-center gap-1.5 py-2 px-4 bg-sky-600 hover:bg-sky-700 text-white rounded-xl text-xs font-bold cursor-pointer disabled:opacity-50">
                {salvando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} {editId === null ? 'Criar' : 'Salvar'}
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
