import { useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Loader2, UserCog, Save, KeyRound } from 'lucide-react';
import * as api from '../api';
import { ApiError, Usuario } from '../api';
import { Toast } from '../types';

interface Props {
  usuario: Usuario;
  onClose: () => void;
  onAtualizado: (u: Usuario) => void;
  addToast: (message: string, type: Toast['type']) => void;
}

const inputCls =
  'w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:bg-slate-100 disabled:text-slate-400';

/**
 * Autogestão do próprio usuário: editar o nome e trocar a senha.
 * O e-mail (credencial de login) é somente leitura — não pode ser alterado aqui.
 */
export default function PerfilModal({ usuario, onClose, onAtualizado, addToast }: Props) {
  const [nome, setNome] = useState(usuario.nome);
  const [senhaAtual, setSenhaAtual] = useState('');
  const [senhaNova, setSenhaNova] = useState('');
  const [senhaConf, setSenhaConf] = useState('');
  const [salvando, setSalvando] = useState(false);

  const trocandoSenha = !!(senhaAtual || senhaNova || senhaConf);
  const nomeMudou = nome.trim() !== usuario.nome && nome.trim().length > 0;

  const salvar = async () => {
    if (trocandoSenha) {
      if (!senhaAtual) {
        addToast('Informe a senha atual.', 'warning');
        return;
      }
      if (senhaNova.length < 4) {
        addToast('A nova senha deve ter ao menos 4 caracteres.', 'warning');
        return;
      }
      if (senhaNova !== senhaConf) {
        addToast('A confirmação da nova senha não confere.', 'warning');
        return;
      }
    }
    if (!nomeMudou && !trocandoSenha) {
      addToast('Nenhuma alteração a salvar.', 'info');
      return;
    }
    setSalvando(true);
    try {
      const atualizado = await api.atualizarPerfil({
        nome: nomeMudou ? nome.trim() : undefined,
        senha_atual: trocandoSenha ? senhaAtual : undefined,
        senha_nova: trocandoSenha ? senhaNova : undefined,
      });
      onAtualizado(atualizado);
      addToast('Perfil atualizado com sucesso.', 'success');
      onClose();
    } catch (err) {
      addToast(err instanceof ApiError ? err.message : 'Falha ao atualizar o perfil.', 'error');
    } finally {
      setSalvando(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl max-w-md w-full max-h-[88vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Cabeçalho */}
        <div className="p-5 border-b border-slate-100 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="h-9 w-9 rounded-xl bg-brand-50 border border-brand-100 flex items-center justify-center shrink-0">
              <UserCog className="h-4.5 w-4.5 text-brand-900" />
            </div>
            <div className="min-w-0">
              <h3 className="text-sm font-bold text-slate-900">Meu acesso</h3>
              <p className="text-[11px] text-slate-500">Gerencie seu nome e senha.</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-5 overflow-y-auto space-y-4">
          <div>
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1">
              Nome
            </label>
            <input value={nome} onChange={(e) => setNome(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1">
              E-mail (login)
            </label>
            <input value={usuario.email} disabled className={inputCls} />
            <p className="text-[10px] text-slate-400 mt-1">
              O e-mail é a sua credencial de login e não pode ser alterado aqui. Fale com um
              administrador se precisar mudá-lo.
            </p>
          </div>

          <div className="pt-1 border-t border-slate-100">
            <div className="flex items-center gap-1.5 text-[10px] font-bold text-slate-400 uppercase tracking-wide mt-3 mb-2">
              <KeyRound className="h-3.5 w-3.5" /> Trocar senha (opcional)
            </div>
            <div className="space-y-2.5">
              <input
                type="password"
                value={senhaAtual}
                onChange={(e) => setSenhaAtual(e.target.value)}
                placeholder="Senha atual"
                autoComplete="current-password"
                className={inputCls}
              />
              <input
                type="password"
                value={senhaNova}
                onChange={(e) => setSenhaNova(e.target.value)}
                placeholder="Nova senha"
                autoComplete="new-password"
                className={inputCls}
              />
              <input
                type="password"
                value={senhaConf}
                onChange={(e) => setSenhaConf(e.target.value)}
                placeholder="Confirmar nova senha"
                autoComplete="new-password"
                className={inputCls}
              />
            </div>
          </div>
        </div>

        <div className="bg-slate-50 px-5 py-4 border-t border-slate-100 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
          <button
            onClick={onClose}
            className="py-2.5 px-5 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer"
          >
            Fechar
          </button>
          <button
            onClick={salvar}
            disabled={salvando}
            className="flex items-center justify-center gap-1.5 py-2.5 px-5 bg-brand-900 hover:bg-brand-950 text-white rounded-xl text-xs font-bold shadow-md shadow-brand-950/10 transition-all cursor-pointer disabled:opacity-60"
          >
            {salvando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {salvando ? 'Salvando…' : 'Salvar'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
