import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { Plus, Trash2, Loader2, Pencil, X, Check, Users, ChevronRight, Mail } from 'lucide-react';
import * as api from '../../api';
import { ApiError, AreaOrg, RateioDisponivel } from '../../api';
import { Toast } from '../../types';

interface Props {
  addToast: (message: string, type: Toast['type']) => void;
}

const inputCls =
  'w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500';

/** Agrupa os processos por categoria (prefixo do tipo) para o checklist. */
function grupoDoTipo(tipo: string): string {
  if (tipo === api.TIPO_CLARO) return 'Telefonia';
  if (tipo.startsWith('pagamento')) return 'Pagamento';
  if (tipo.startsWith('coparticipacao')) return 'Coparticipação';
  return 'Outros';
}

export default function SetoresConfig({ addToast }: Props) {
  const [areas, setAreas] = useState<AreaOrg[]>([]);
  const [rateios, setRateios] = useState<RateioDisponivel[]>([]);
  const [carregando, setCarregando] = useState(true);

  // Criação e edição no MESMO modal (padrão das outras telas de cadastro):
  // `editId` nulo = nova área. O nome e os e-mails de cópia são atributos da
  // área, então se editam juntos; a matriz de processos continua na área
  // expandida, porque lá cada marcação já grava sozinha.
  const [modalAberto, setModalAberto] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [fNome, setFNome] = useState('');
  const [fCopia, setFCopia] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [abertos, setAbertos] = useState<Set<number>>(new Set());

  const erro = (err: unknown, fallback: string) =>
    addToast(err instanceof ApiError ? err.message : fallback, 'error');
  const recarregar = () => api.listarAreas().then(setAreas).catch((e) => erro(e, 'Falha ao carregar áreas.'));

  useEffect(() => {
    Promise.all([api.listarAreas(), api.listarRateiosDisponiveis()])
      .then(([a, r]) => { setAreas(a); setRateios(r); })
      .catch((e) => erro(e, 'Falha ao carregar dados.'))
      .finally(() => setCarregando(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Processos agrupados por categoria (para o checklist da área expandida).
  const grupos = useMemo(() => {
    const mapa = new Map<string, RateioDisponivel[]>();
    for (const r of rateios) {
      const g = grupoDoTipo(r.tipo);
      if (!mapa.has(g)) mapa.set(g, []);
      mapa.get(g)!.push(r);
    }
    return [...mapa.entries()];
  }, [rateios]);

  const abrir = (id: number) =>
    setAbertos((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  const toggle = async (area: AreaOrg, tipo: string) => {
    const novos = area.rateios.includes(tipo)
      ? area.rateios.filter((t) => t !== tipo)
      : [...area.rateios, tipo];
    setAreas((prev) => prev.map((a) => (a.id === area.id ? { ...a, rateios: novos } : a)));
    try {
      await api.atualizarArea(area.id, area.nome, novos, area.emails_copia);
    } catch (err) { erro(err, 'Falha ao atualizar a área.'); recarregar(); }
  };

  const abrirNova = () => { setEditId(null); setFNome(''); setFCopia(''); setModalAberto(true); };
  const abrirEdicao = (a: AreaOrg) => {
    setEditId(a.id); setFNome(a.nome); setFCopia(a.emails_copia || ''); setModalAberto(true);
  };
  const fechar = () => { if (!salvando) setModalAberto(false); };

  const salvar = async () => {
    if (!fNome.trim()) { addToast('Informe o nome da área.', 'warning'); return; }
    setSalvando(true);
    try {
      if (editId === null) {
        const nova = await api.criarArea(fNome.trim(), [], fCopia.trim());
        await recarregar();
        // Abre a nova área: sem processos marcados ela não dá acesso a nada.
        setAbertos((s) => new Set(s).add(nova.id));
        addToast('Área criada. Selecione os processos que ela acessa.', 'success');
      } else {
        const atual = areas.find((a) => a.id === editId);
        await api.atualizarArea(editId, fNome.trim(), atual?.rateios ?? [], fCopia.trim());
        await recarregar();
        addToast('Área salva.', 'success');
      }
      setModalAberto(false);
    } catch (err) {
      // E-mail inválido volta como 422 do backend: o modal fica aberto com o que
      // foi digitado, para corrigir sem redigitar.
      erro(err, 'Falha ao salvar a área.');
    } finally { setSalvando(false); }
  };
  const remover = async (a: AreaOrg) => {
    if (a.num_usuarios > 0) { addToast(`A área "${a.nome}" tem ${a.num_usuarios} usuário(s) vinculado(s).`, 'warning'); return; }
    try { await api.removerArea(a.id); await recarregar(); addToast('Área removida.', 'success'); }
    catch (err) { erro(err, 'Falha ao remover a área.'); }
  };

  if (carregando) {
    return <div className="h-40 flex items-center justify-center text-slate-400"><Loader2 className="h-6 w-6 animate-spin" /></div>;
  }

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Setores e permissões</h2>
          <p className="text-xs text-slate-500">
            Cada área (setor) agrupa usuários e define <strong>quais processos ela acessa</strong>.
            Abra uma área para marcar seus processos.
          </p>
        </div>
        <button onClick={abrirNova}
          className="flex items-center gap-1.5 py-2 px-4 bg-sky-600 hover:bg-sky-700 text-white rounded-xl text-xs font-bold shadow-lg shadow-sky-600/20 transition-all cursor-pointer shrink-0">
          <Plus className="h-4 w-4" /> Nova área
        </button>
      </div>

      {/* Lista de áreas (accordion) */}
      <div className="space-y-2.5">
        {areas.map((a) => {
          const aberto = abertos.has(a.id);
          return (
            <div key={a.id} className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              {/* Cabeçalho: nome + resumo + ações */}
              <div className="flex items-center gap-3 p-4 px-5">
                <button onClick={() => abrir(a.id)} className="flex items-center gap-2.5 flex-1 min-w-0 cursor-pointer text-left">
                  <ChevronRight className={`h-4 w-4 text-slate-400 shrink-0 transition-transform ${aberto ? 'rotate-90' : ''}`} />
                  <span className="text-sm font-bold text-slate-900 truncate">{a.nome}</span>
                  <span className="text-[11px] text-slate-400 shrink-0">
                    {a.rateios.length} {a.rateios.length === 1 ? 'processo' : 'processos'}
                    <span className="mx-1.5 text-slate-300">·</span>
                    <span className="inline-flex items-center gap-1"><Users className="h-3 w-3" />{a.num_usuarios}</span>
                    {/* Cópia cadastrada aparece como indício no cabeçalho; os
                        endereços ficam no modal, onde são editados. */}
                    {a.emails_copia && (
                      <>
                        <span className="mx-1.5 text-slate-300">·</span>
                        <span className="inline-flex items-center gap-1" title={a.emails_copia}>
                          <Mail className="h-3 w-3" />
                          {a.emails_copia.split(',').filter((e) => e.trim()).length}
                        </span>
                      </>
                    )}
                  </span>
                </button>
                <div className="flex gap-1 shrink-0">
                  <button onClick={() => abrirEdicao(a)} className="p-1.5 text-slate-400 hover:text-sky-600 hover:bg-slate-50 rounded-lg cursor-pointer" title="Editar"><Pencil className="h-4 w-4" /></button>
                  <button onClick={() => remover(a)} className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-slate-50 rounded-lg cursor-pointer" title="Remover"><Trash2 className="h-4 w-4" /></button>
                </div>
              </div>

              {/* Checklist de processos (agrupado por categoria) */}
              {aberto && (
                <div className="border-t border-slate-100 bg-slate-50/40 p-4 px-5 space-y-4">
                  {grupos.length === 0 && <p className="text-[11px] text-slate-400">Nenhum processo disponível.</p>}
                  {grupos.map(([grupo, rs]) => (
                    <div key={grupo}>
                      <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">{grupo}</div>
                      <div className="space-y-1">
                        {rs.map((r) => {
                          const on = a.rateios.includes(r.tipo);
                          return (
                            <button key={r.tipo} onClick={() => toggle(a, r.tipo)}
                              className={`w-full flex items-start gap-2.5 text-left rounded-lg px-3 py-2 border transition-colors cursor-pointer ${
                                on ? 'bg-sky-50 border-sky-200' : 'bg-white border-slate-200 hover:bg-slate-50'
                              }`}>
                              <span className={`h-4 w-4 rounded border flex items-center justify-center shrink-0 mt-0.5 ${on ? 'bg-sky-600 border-sky-600' : 'border-slate-300'}`}>
                                {on && <Check className="h-3 w-3 text-white" />}
                              </span>
                              <span className="min-w-0">
                                <span className={`block text-xs font-semibold ${on ? 'text-sky-800' : 'text-slate-700'}`}>{r.nome}</span>
                                {r.descricao && <span className="block text-[11px] text-slate-400 leading-snug">{r.descricao}</span>}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {areas.length === 0 && <p className="text-sm text-slate-400 text-center py-8">Nenhuma área cadastrada.</p>}
      </div>

      {modalAberto && createPortal(
        <div className="fixed inset-0 z-40 bg-slate-900/40 flex items-start justify-center p-4 overflow-y-auto" onClick={fechar}>
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full my-8" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-5 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900">{editId === null ? 'Nova área' : 'Editar área'}</h3>
              <button onClick={fechar} className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 cursor-pointer"><X className="h-4 w-4" /></button>
            </div>
            <div className="p-5 space-y-3">
              <label className="block text-[11px] font-semibold text-slate-500">Nome do setor
                <input value={fNome} onChange={(e) => setFNome(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && salvar()}
                  placeholder="Financeiro" className={inputCls} autoFocus />
              </label>
              <label className="block text-[11px] font-semibold text-slate-500">Cópia nas notificações
                <input value={fCopia} onChange={(e) => setFCopia(e.target.value)}
                  placeholder="responsavel@financeflow.local, gestor@financeflow.local" className={inputCls} />
                <span className="mt-1 block text-[11px] font-normal text-slate-400">
                  Entram em cópia nos e-mails dos processos desta área e recebem a resposta do
                  departamento fiscal. Separe vários por vírgula; deixe vazio para notificar só o
                  fiscal.
                </span>
              </label>
              {editId === null && (
                <p className="text-[11px] text-slate-400">
                  Os processos que a área acessa são marcados depois de criá-la, na própria lista.
                </p>
              )}
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
