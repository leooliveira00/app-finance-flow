import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  HeartPulse,
  Banknote,
  Users,
  Layers,
  Lock,
  Building2,
  Briefcase,
  Search,
  Smartphone,
  Truck,
  Workflow,
  Mail,
} from 'lucide-react';
import * as api from '../api';
import { Usuario } from '../api';
import * as perm from '../permissoes';
import { Toast } from '../types';
import CoparticipacaoConfig from './config/CoparticipacaoConfig';
import PagamentoConfig from './config/PagamentoConfig';
import CentroCustoConfig from './config/CentroCustoConfig';
import EmpresasConfig from './config/EmpresasConfig';
import FornecedoresConfig from './config/FornecedoresConfig';
import ColaboradoresPjConfig from './config/ColaboradoresPjConfig';
import UsuariosConfig from './config/UsuariosConfig';
import SetoresConfig from './config/SetoresConfig';
import ProcessosConfig from './config/ProcessosConfig';
import NotificacoesConfig from './config/NotificacoesConfig';
import TelefoniaConfig from './config/TelefoniaConfig';

interface Props {
  usuario: Usuario;
  addToast: (message: string, type: Toast['type']) => void;
}

interface Secao {
  id: string;
  grupo: string;
  label: string;
  icon: typeof HeartPulse;
  soAdmin?: boolean; // só admin global (gestão organizacional)
  tipos?: string[]; // rateios que a seção configura (filtra por área)
  render: () => ReactNode;
}

// Ordem canônica dos grupos na navegação.
const GRUPOS_ORDEM = ['Rateios', 'Cadastros', 'Organização'];

const semAcento = (s: string) =>
  s
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();

export default function ConfigScreen({ usuario, addToast }: Props) {
  const admin = perm.ehAdmin(usuario);
  const podeEditarCadastro = perm.podeEditarCadastro(usuario);

  // Rateios que o usuário enxerga (para filtrar as seções específicas de rateio).
  // null = ainda carregando (mostra otimista até chegar).
  const [tiposVisiveis, setTiposVisiveis] = useState<Set<string> | null>(null);
  const [busca, setBusca] = useState('');

  useEffect(() => {
    api
      .getModulos(true)
      .then((mods) => setTiposVisiveis(new Set(mods.map((m) => m.tipo))))
      .catch(() => setTiposVisiveis(new Set()));
  }, []);

  const secoes: Secao[] = useMemo(() => {
    const lista: Secao[] = [
      {
        id: 'copart',
        grupo: 'Rateios',
        label: 'Coparticipação',
        icon: HeartPulse,
        tipos: ['coparticipacao-plano-saude'],
        render: () => <CoparticipacaoConfig admin={podeEditarCadastro} addToast={addToast} />,
      },
      {
        id: 'pagamento',
        grupo: 'Rateios',
        label: 'Pagamento',
        icon: Banknote,
        tipos: ['pagamento-unimed', 'pagamento-bradesco', 'pagamento-coparticipacao-unimed'],
        render: () => <PagamentoConfig />,
      },
      {
        id: 'telefonia',
        grupo: 'Rateios',
        label: 'Telefonia',
        icon: Smartphone,
        tipos: [api.TIPO_CLARO],
        // Quem mantém é a área dona do processo (TI): admin global OU quem enxerga
        // o rateio da Claro. O backend aplica a mesma regra nas escritas.
        render: () => (
          <TelefoniaConfig
            podeEditar={admin || !!tiposVisiveis?.has(api.TIPO_CLARO)}
            addToast={addToast}
          />
        ),
      },
      {
        id: 'centros-custo',
        grupo: 'Cadastros',
        label: 'Centros de custo',
        icon: Building2,
        render: () => <CentroCustoConfig admin={podeEditarCadastro} addToast={addToast} />,
      },
      {
        id: 'empresas',
        grupo: 'Cadastros',
        label: 'Empresas',
        icon: Building2,
        render: () => <EmpresasConfig admin={podeEditarCadastro} addToast={addToast} />,
      },
      {
        id: 'fornecedores',
        grupo: 'Cadastros',
        label: 'Fornecedores',
        icon: Truck,
        render: () => <FornecedoresConfig admin={podeEditarCadastro} addToast={addToast} />,
      },
      {
        id: 'pj',
        grupo: 'Cadastros',
        label: 'Colaboradores PJ',
        icon: Briefcase,
        render: () => <ColaboradoresPjConfig admin={podeEditarCadastro} addToast={addToast} />,
      },
      {
        id: 'usuarios',
        grupo: 'Organização',
        label: 'Usuários',
        icon: Users,
        soAdmin: true,
        render: () => <UsuariosConfig usuarioAtual={usuario.email} addToast={addToast} />,
      },
      {
        // Disponibilidade vale para a ferramenta inteira, então fica em
        // Organização, e não junto dos cadastros de cada rateio.
        id: 'processos',
        grupo: 'Organização',
        label: 'Processos',
        icon: Workflow,
        soAdmin: true,
        render: () => <ProcessosConfig addToast={addToast} />,
      },
      {
        id: 'notificacoes',
        grupo: 'Organização',
        label: 'Notificações',
        icon: Mail,
        soAdmin: true,
        render: () => <NotificacoesConfig admin={admin} addToast={addToast} />,
      },
      {
        id: 'setores',
        grupo: 'Organização',
        label: 'Setores e permissões',
        icon: Layers,
        soAdmin: true,
        render: () => <SetoresConfig addToast={addToast} />,
      },
    ];
    return lista.filter((s) => {
      if (s.soAdmin && !admin) return false;
      // Seção específica de rateio: não-admin só vê os rateios das suas áreas.
      if (s.tipos && !admin && tiposVisiveis) return s.tipos.some((t) => tiposVisiveis.has(t));
      return true;
    });
  }, [admin, podeEditarCadastro, usuario.email, addToast, tiposVisiveis]);

  const [ativa, setAtiva] = useState('copart');
  // A seção ativa é resolvida sobre TODAS as seções visíveis (não sobre a busca),
  // para o painel continuar exibido mesmo com um filtro de busca aplicado.
  const secaoAtiva = secoes.find((s) => s.id === ativa) ?? secoes[0];

  // Busca: filtra a navegação por rótulo/grupo (ignora acento e caixa).
  const filtradas = useMemo(() => {
    const q = semAcento(busca.trim());
    if (!q) return secoes;
    return secoes.filter((s) => semAcento(s.label).includes(q) || semAcento(s.grupo).includes(q));
  }, [secoes, busca]);

  const grupos = useMemo(() => {
    const mapa = new Map<string, Secao[]>();
    for (const s of filtradas) {
      if (!mapa.has(s.grupo)) mapa.set(s.grupo, []);
      mapa.get(s.grupo)!.push(s);
    }
    return GRUPOS_ORDEM.filter((g) => mapa.has(g)).map(
      (g) => [g, mapa.get(g)!] as [string, Secao[]],
    );
  }, [filtradas]);

  return (
    <div className="animate-fade-in space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Configurações</h1>
        <p className="text-xs text-slate-500">
          Parâmetros dos rateios, cadastros compartilhados e gestão de acesso.
        </p>
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        {/* Sub-navegação */}
        <nav className="lg:w-60 lg:shrink-0">
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-2.5 lg:sticky lg:top-4 space-y-3">
            {/* Busca */}
            <div className="relative">
              <Search className="h-3.5 w-3.5 text-slate-400 absolute inset-y-0 left-2.5 my-auto" />
              <input
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                placeholder="Buscar configuração..."
                className="w-full pl-8 pr-2 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-medium placeholder-slate-400 text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>

            {grupos.map(([grupo, itens]) => (
              <div key={grupo}>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-2.5 py-1.5">
                  {grupo}
                </p>
                <div className="space-y-0.5">
                  {itens.map((s) => {
                    const Icone = s.icon;
                    const on = s.id === secaoAtiva?.id;
                    return (
                      <button
                        key={s.id}
                        onClick={() => setAtiva(s.id)}
                        className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm transition-colors cursor-pointer ${
                          on
                            ? 'bg-sky-50 text-sky-700 font-bold'
                            : 'text-slate-600 hover:bg-slate-50 font-medium'
                        }`}
                      >
                        <Icone
                          className={`h-4 w-4 shrink-0 ${on ? 'text-sky-600' : 'text-slate-400'}`}
                        />
                        <span className="truncate text-left">{s.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
            {grupos.length === 0 && (
              <p className="text-[11px] text-slate-400 text-center py-4">
                Nenhuma configuração encontrada.
              </p>
            )}
          </div>
        </nav>

        {/* Conteúdo da seção ativa */}
        <div className="flex-1 min-w-0">
          {!podeEditarCadastro && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-3.5 flex items-start gap-2 text-xs text-amber-700 mb-5">
              <Lock className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
              <span>Você está no modo leitura. Edição de cadastros requer admin da área.</span>
            </div>
          )}
          {secaoAtiva?.render()}
        </div>
      </div>
    </div>
  );
}
