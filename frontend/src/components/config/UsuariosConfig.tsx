import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Plus,
  Trash2,
  Loader2,
  Pencil,
  X,
  Check,
  ShieldCheck,
  User,
  UserCheck,
  UserX,
} from 'lucide-react';
import * as api from '../../api';
import { ApiError, AreaOrg, UsuarioOrg, AreaNivel, NivelArea } from '../../api';
import { Toast } from '../../types';

const NIVEL_LABEL: Record<NivelArea, string> = {
  operador: 'Operador',
  admin_area: 'Admin da área',
};

interface Props {
  usuarioAtual: string;
  addToast: (message: string, type: Toast['type']) => void;
}

const inputCls =
  'w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500';

const NIVEIS: NivelArea[] = ['operador', 'admin_area'];

function AreasPicker({
  areas,
  selecionados,
  onToggle,
  onSetNivel,
  disabled,
}: {
  areas: AreaOrg[];
  selecionados: AreaNivel[];
  onToggle: (nome: string) => void;
  onSetNivel: (nome: string, nivel: NivelArea) => void;
  disabled?: boolean;
}) {
  if (disabled)
    return (
      <span className="text-[11px] text-slate-400 italic">
        Admin enxerga todos os rateios — áreas não se aplicam.
      </span>
    );
  return (
    <div className="space-y-2">
      {areas.map((a) => {
        const sel = selecionados.find((s) => s.area === a.nome);
        const on = !!sel;
        return (
          <div key={a.id} className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => onToggle(a.nome)}
              className={`flex items-center gap-1.5 text-xs font-semibold rounded-lg px-2.5 py-1.5 border transition-colors cursor-pointer ${
                on
                  ? 'bg-sky-50 text-sky-700 border-sky-200'
                  : 'bg-white text-slate-500 border-slate-200 hover:bg-slate-50'
              }`}
            >
              <span
                className={`h-3.5 w-3.5 rounded flex items-center justify-center border ${on ? 'bg-sky-600 border-sky-600' : 'border-slate-300'}`}
              >
                {on && <Check className="h-2.5 w-2.5 text-white" />}
              </span>
              {a.nome}
            </button>
            {on && sel && (
              <div className="flex rounded-lg border border-slate-200 overflow-hidden">
                {NIVEIS.map((nivel) => {
                  const ativo = sel.nivel === nivel;
                  return (
                    <button
                      key={nivel}
                      type="button"
                      onClick={() => onSetNivel(a.nome, nivel)}
                      title={
                        nivel === 'admin_area'
                          ? 'Audita salário/teto e edita o cadastro da área'
                          : 'Opera e envia ao ERP; não vê salário/teto'
                      }
                      className={`flex items-center gap-1 text-[11px] font-semibold px-2 py-1.5 transition-colors cursor-pointer ${
                        ativo
                          ? 'bg-sky-600 text-white'
                          : 'bg-white text-slate-500 hover:bg-slate-50'
                      }`}
                    >
                      {nivel === 'admin_area' ? (
                        <ShieldCheck className="h-3 w-3" />
                      ) : (
                        <User className="h-3 w-3" />
                      )}
                      {NIVEL_LABEL[nivel]}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
      {areas.length > 0 && (
        <p className="text-[10px] text-slate-400 leading-relaxed pt-1">
          <strong className="text-slate-500">Operador</strong>: opera e envia ao ERP (não vê
          salário/teto). · <strong className="text-slate-500">Admin da área</strong>: também audita
          salário/teto e edita os cadastros da área.
        </p>
      )}
      {areas.length === 0 && (
        <span className="text-[11px] text-slate-400 italic">Nenhuma área cadastrada ainda.</span>
      )}
    </div>
  );
}

export default function UsuariosConfig({ usuarioAtual, addToast }: Props) {
  const [usuarios, setUsuarios] = useState<UsuarioOrg[]>([]);
  const [areas, setAreas] = useState<AreaOrg[]>([]);
  const [carregando, setCarregando] = useState(true);

  // Modal (criar/editar). editId = null -> criando; número -> editando.
  const [modalAberto, setModalAberto] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [fNome, setFNome] = useState('');
  const [fEmail, setFEmail] = useState('');
  const [fSenha, setFSenha] = useState('');
  const [fAdmin, setFAdmin] = useState(false);
  const [fAtivo, setFAtivo] = useState(true);
  const [fAreas, setFAreas] = useState<AreaNivel[]>([]);
  const [salvando, setSalvando] = useState(false);

  const erro = (err: unknown, fallback: string) =>
    addToast(err instanceof ApiError ? err.message : fallback, 'error');
  const recarregar = () =>
    api
      .listarUsuarios()
      .then(setUsuarios)
      .catch((e) => erro(e, 'Falha ao carregar usuários.'));

  useEffect(() => {
    Promise.all([api.listarUsuarios(), api.listarAreas()])
      .then(([u, a]) => {
        setUsuarios(u);
        setAreas(a);
      })
      .catch((e) => erro(e, 'Falha ao carregar dados.'))
      .finally(() => setCarregando(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (nome: string) =>
    setFAreas((lista) =>
      lista.some((x) => x.area === nome)
        ? lista.filter((x) => x.area !== nome)
        : [...lista, { area: nome, nivel: 'operador' }],
    );
  const setNivel = (nome: string, nivel: NivelArea) =>
    setFAreas((lista) => lista.map((x) => (x.area === nome ? { ...x, nivel } : x)));

  const abrirNovo = () => {
    setEditId(null);
    setFNome('');
    setFEmail('');
    setFSenha('');
    setFAdmin(false);
    setFAtivo(true);
    setFAreas([]);
    setModalAberto(true);
  };
  const abrirEdicao = (u: UsuarioOrg) => {
    setEditId(u.id);
    setFNome(u.nome);
    setFEmail(u.email);
    setFSenha('');
    setFAdmin(u.admin);
    setFAtivo(u.ativo);
    setFAreas(u.areas);
    setModalAberto(true);
  };
  const fechar = () => {
    if (!salvando) setModalAberto(false);
  };

  const salvar = async () => {
    if (!fNome.trim() || !fEmail.trim() || (editId === null && !fSenha)) {
      addToast('Preencha nome, e-mail e senha.', 'warning');
      return;
    }
    setSalvando(true);
    try {
      if (editId === null) {
        await api.criarUsuario({
          email: fEmail.trim(),
          nome: fNome.trim(),
          senha: fSenha,
          admin: fAdmin,
          areas: fAdmin ? [] : fAreas,
        });
        addToast('Usuário criado.', 'success');
      } else {
        await api.atualizarUsuario(editId, {
          nome: fNome.trim(),
          email: fEmail.trim(),
          admin: fAdmin,
          ativo: fAtivo,
          areas: fAdmin ? [] : fAreas,
          senha: fSenha || undefined,
        });
        addToast('Usuário atualizado.', 'success');
      }
      setModalAberto(false);
      await recarregar();
    } catch (err) {
      erro(err, 'Falha ao salvar o usuário.');
    } finally {
      setSalvando(false);
    }
  };

  const remover = async (u: UsuarioOrg) => {
    try {
      await api.removerUsuario(u.id);
      await recarregar();
      addToast('Usuário removido.', 'success');
    } catch (err) {
      erro(err, 'Falha ao remover o usuário.');
    }
  };
  // Inativa/reativa: usuário inativo não consegue logar (o backend filtra no login).
  const toggleAtivo = async (u: UsuarioOrg) => {
    try {
      await api.atualizarUsuario(u.id, {
        nome: u.nome,
        email: u.email,
        admin: u.admin,
        ativo: !u.ativo,
        areas: u.areas,
      });
      await recarregar();
      addToast(
        u.ativo ? `${u.nome} inativado (não poderá entrar).` : `${u.nome} reativado.`,
        'success',
      );
    } catch (err) {
      erro(err, 'Falha ao alterar o status do usuário.');
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
          <h2 className="text-lg font-bold text-slate-900">Usuários</h2>
          <p className="text-xs text-slate-500">
            Contas de acesso à plataforma. Admins enxergam todos os rateios; os demais, os das suas
            áreas.
          </p>
        </div>
        <button
          onClick={abrirNovo}
          className="flex items-center gap-1.5 py-2 px-4 bg-sky-600 hover:bg-sky-700 text-white rounded-xl text-xs font-bold shadow-lg shadow-sky-600/20 transition-all cursor-pointer shrink-0"
        >
          <Plus className="h-4 w-4" /> Novo usuário
        </button>
      </div>

      {/* Lista */}
      <div className="space-y-3">
        {usuarios.map((u) => (
          <div
            key={u.id}
            className={`bg-white rounded-xl border border-slate-200 shadow-sm p-5 ${!u.ativo ? 'opacity-60' : ''}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <User className="h-4 w-4 text-slate-400 shrink-0" />
                  <span className="text-sm font-bold text-slate-900">{u.nome}</span>
                  <span className="text-xs font-mono text-slate-400">{u.email}</span>
                  {u.admin && (
                    <span className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide bg-indigo-50 text-indigo-600 border border-indigo-200 rounded px-2 py-0.5">
                      <ShieldCheck className="h-3 w-3" /> Admin
                    </span>
                  )}
                  {!u.ativo && (
                    <span className="text-[10px] font-bold uppercase tracking-wide bg-slate-100 text-slate-500 border border-slate-200 rounded px-2 py-0.5">
                      Inativo
                    </span>
                  )}
                </div>
                {!u.admin && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {u.areas.length === 0 && (
                      <span className="text-[11px] text-amber-600 italic">
                        Sem áreas — não vê nenhum rateio
                      </span>
                    )}
                    {u.areas.map((a) => (
                      <span
                        key={a.area}
                        className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide bg-slate-100 text-slate-600 border border-slate-200 rounded px-2 py-0.5"
                      >
                        {a.area}
                        <span
                          className={`flex items-center gap-0.5 normal-case ${a.nivel === 'admin_area' ? 'text-indigo-600' : 'text-slate-400'}`}
                        >
                          ·{' '}
                          {a.nivel === 'admin_area' ? (
                            <ShieldCheck className="h-2.5 w-2.5" />
                          ) : (
                            <User className="h-2.5 w-2.5" />
                          )}
                          {NIVEL_LABEL[a.nivel]}
                        </span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex gap-1 shrink-0">
                <button
                  onClick={() => toggleAtivo(u)}
                  disabled={u.email === usuarioAtual}
                  className={`p-1.5 text-slate-400 hover:bg-slate-50 rounded-lg transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed ${u.ativo ? 'hover:text-amber-600' : 'hover:text-emerald-600'}`}
                  title={
                    u.email === usuarioAtual
                      ? 'Você não pode inativar a si mesmo'
                      : u.ativo
                        ? 'Inativar (bloqueia o login)'
                        : 'Reativar'
                  }
                >
                  {u.ativo ? <UserX className="h-4 w-4" /> : <UserCheck className="h-4 w-4" />}
                </button>
                <button
                  onClick={() => abrirEdicao(u)}
                  className="p-1.5 text-slate-400 hover:text-sky-600 hover:bg-slate-50 rounded-lg transition-colors cursor-pointer"
                  title="Editar"
                >
                  <Pencil className="h-4 w-4" />
                </button>
                <button
                  onClick={() => remover(u)}
                  disabled={u.email === usuarioAtual}
                  className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-slate-50 rounded-lg transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                  title={u.email === usuarioAtual ? 'Você não pode remover a si mesmo' : 'Remover'}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        ))}
        {usuarios.length === 0 && (
          <p className="text-sm text-slate-400 text-center py-8">Nenhum usuário cadastrado.</p>
        )}
      </div>

      {/* Modal criar/editar */}
      {modalAberto &&
        createPortal(
          <div
            className="fixed inset-0 z-40 bg-slate-900/40 flex items-start justify-center p-4 overflow-y-auto"
            onClick={fechar}
          >
            <div
              className="bg-white rounded-2xl shadow-xl max-w-2xl w-full my-8"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between p-5 border-b border-slate-100">
                <h3 className="text-sm font-bold text-slate-900">
                  {editId === null ? 'Novo usuário' : 'Editar usuário'}
                </h3>
                <button
                  onClick={fechar}
                  className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 cursor-pointer"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="p-5 space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1">
                      Nome
                    </label>
                    <input
                      value={fNome}
                      onChange={(e) => setFNome(e.target.value)}
                      placeholder="Nome completo"
                      className={inputCls}
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1">
                      E-mail (login)
                    </label>
                    <input
                      type="email"
                      value={fEmail}
                      onChange={(e) => setFEmail(e.target.value)}
                      placeholder="ex.: joao.silva@financeflow.local"
                      className={inputCls}
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1">
                      {editId === null ? 'Senha' : 'Nova senha (opcional)'}
                    </label>
                    <input
                      type="password"
                      value={fSenha}
                      onChange={(e) => setFSenha(e.target.value)}
                      placeholder={
                        editId === null ? 'Senha inicial' : 'Deixe em branco para manter'
                      }
                      className={inputCls}
                    />
                  </div>
                </div>
                <div className="flex flex-wrap gap-4">
                  <label className="flex items-center gap-2 text-xs font-semibold text-slate-600 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={fAdmin}
                      onChange={(e) => setFAdmin(e.target.checked)}
                      className="accent-sky-600 h-4 w-4"
                    />
                    Administrador (vê todos os rateios e gerencia cadastros)
                  </label>
                  {editId !== null && (
                    <label className="flex items-center gap-2 text-xs font-semibold text-slate-600 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={fAtivo}
                        onChange={(e) => setFAtivo(e.target.checked)}
                        className="accent-sky-600 h-4 w-4"
                      />{' '}
                      Ativo
                    </label>
                  )}
                </div>
                <div>
                  <span className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5">
                    Áreas e nível de acesso
                  </span>
                  <AreasPicker
                    areas={areas}
                    selecionados={fAreas}
                    onToggle={toggle}
                    onSetNivel={setNivel}
                    disabled={fAdmin}
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 p-5 border-t border-slate-100">
                <button
                  onClick={fechar}
                  disabled={salvando}
                  className="py-2 px-4 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer disabled:opacity-50"
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
                  {editId === null ? 'Criar usuário' : 'Salvar'}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
