import { ActiveTab } from '../types';
import {
  LayoutDashboard,
  History,
  Settings,
  LogOut,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import logoSymbol from '../img/logo-financeflow.png';

interface SidebarProps {
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;
  onLogout: () => void;
  onOpenPerfil: () => void;
  userName: string;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export default function Sidebar({
  activeTab,
  setActiveTab,
  onLogout,
  onOpenPerfil,
  userName,
  collapsed,
  onToggleCollapse,
}: SidebarProps) {
  const menuItems = [
    { id: 'dashboard' as ActiveTab, label: 'Painel', icon: LayoutDashboard },
    { id: 'historico' as ActiveTab, label: 'Histórico', icon: History },
    { id: 'configuracoes' as ActiveTab, label: 'Configurações', icon: Settings },
  ];

  // Iniciais do usuário para o avatar (ex.: "Recursos Humanos" -> "RH").
  const initials = userName
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase();

  return (
    <aside
      className={`bg-brand-950 text-white flex flex-col fixed inset-y-0 left-0 z-20 shadow-xl border-r border-brand-900 transition-[width] duration-300 ease-in-out ${
        collapsed ? 'w-20' : 'w-64'
      }`}
    >
      {/* Brand Header */}
      <div
        className={`flex flex-col items-center justify-center border-b border-brand-900 relative ${collapsed ? 'h-16 px-0 gap-0' : 'px-4 py-5 gap-3'}`}
      >
        {/* Logo (símbolo em azul, fundo transparente) direto sobre a sidebar */}
        <img
          src={logoSymbol}
          alt="FinanceFlow"
          className={`object-contain ${collapsed ? 'h-[47px] w-auto' : 'h-[73px] w-auto'}`}
        />
        {!collapsed && (
          <>
            {/* Fio separador e o nome em uma linha, com entreletra larga. O `pl`
                compensa o espaço do último caractere, que desloca o texto ao
                centralizar. */}
            <span aria-hidden="true" className="h-px w-16 bg-white/20" />
            <span className="text-lg font-medium tracking-[0.3em] pl-[0.3em] text-white/90">
              FinanceFlow
            </span>
          </>
        )}

        {/* Botão de colapso — fixado na borda direita do sidebar */}
        <button
          onClick={onToggleCollapse}
          title={collapsed ? 'Expandir menu' : 'Recolher menu'}
          aria-label={collapsed ? 'Expandir menu' : 'Recolher menu'}
          className="absolute -right-3 top-1/2 -translate-y-1/2 z-30 h-6 w-6 rounded-full bg-white text-brand-900 border border-brand-200 shadow-md flex items-center justify-center hover:bg-brand-50 hover:text-brand-700 transition-colors cursor-pointer"
        >
          {collapsed ? (
            <ChevronRight className="h-3.5 w-3.5" />
          ) : (
            <ChevronLeft className="h-3.5 w-3.5" />
          )}
        </button>
      </div>

      {/* Navigation */}
      <nav
        className={`flex-1 py-6 space-y-1.5 overflow-y-auto overflow-x-hidden ${collapsed ? 'px-2.5' : 'px-4'}`}
      >
        {!collapsed && (
          <span className="px-3 text-[10px] font-bold text-brand-400 uppercase tracking-wider block mb-3">
            Navegação
          </span>
        )}

        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              id={`nav-${item.id}`}
              onClick={() => setActiveTab(item.id)}
              title={collapsed ? item.label : undefined}
              className={`w-full flex items-center rounded-xl text-sm font-medium transition-all duration-150 cursor-pointer ${
                collapsed ? 'justify-center px-0 py-3' : 'gap-3 px-3.5 py-2.5'
              } ${
                isActive
                  ? 'bg-brand-900 text-white shadow-md shadow-brand-950/20'
                  : 'text-brand-200 hover:bg-brand-900/40 hover:text-white'
              }`}
            >
              <Icon
                className={`h-4.5 w-4.5 shrink-0 ${isActive ? 'text-white' : 'text-brand-300'}`}
              />
              {!collapsed && item.label}
            </button>
          );
        })}
      </nav>

      {/* User Status / Bottom Actions */}
      <div className={`border-t border-brand-900 bg-brand-950 ${collapsed ? 'p-2.5' : 'p-4'}`}>
        {collapsed ? (
          <button
            onClick={onOpenPerfil}
            title={`Gerenciar o acesso de ${userName}`}
            className="mx-auto mb-2 h-9 w-9 rounded-full bg-brand-800 hover:bg-brand-700 text-white flex items-center justify-center text-[11px] font-bold transition-colors cursor-pointer"
          >
            {initials}
          </button>
        ) : (
          <button
            onClick={onOpenPerfil}
            title="Gerenciar meu acesso"
            className="w-full px-3 py-2.5 rounded-xl bg-brand-900/30 hover:bg-brand-900/60 border border-brand-900/50 flex items-center gap-2.5 mb-3 transition-colors cursor-pointer text-left"
          >
            <div className="h-8 w-8 shrink-0 rounded-full bg-brand-800 text-white flex items-center justify-center text-[11px] font-bold">
              {initials}
            </div>
            <div className="flex flex-col min-w-0">
              <span className="text-[11px] font-medium text-brand-300">Meu acesso</span>
              <span className="text-xs font-semibold text-white truncate">{userName}</span>
            </div>
          </button>
        )}

        <button
          onClick={onLogout}
          title={collapsed ? 'Desconectar painel' : undefined}
          className={`w-full flex items-center rounded-xl text-xs font-semibold text-rose-300 hover:bg-rose-950/40 hover:text-rose-200 transition-colors cursor-pointer ${
            collapsed ? 'justify-center px-0 py-2.5' : 'gap-3 px-3.5 py-2'
          }`}
        >
          <LogOut className="h-4 w-4 shrink-0 text-rose-400" />
          {!collapsed && 'Desconectar painel'}
        </button>

        {/* Versão do build. Congelada em build-time pelo vite.config.ts a partir
            do package.json, que o semantic-release mantém em dia. O sufixo
            "-dev" separa o que roda no servidor de desenvolvimento do que saiu
            de uma imagem publicada. Oculta com a sidebar recolhida. */}
        {!collapsed && (
          <p
            title="Versão da aplicação"
            className="mt-3 text-center text-[10px] font-mono text-brand-400/70"
          >
            v{__APP_VERSION__}
            {import.meta.env.PROD ? '' : '-dev'}
          </p>
        )}
      </div>
    </aside>
  );
}
