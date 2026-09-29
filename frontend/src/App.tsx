/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useEffect, useRef, useState } from 'react';
import { ActiveTab, ViewState, Toast } from './types';
import * as api from './api';
import { Usuario, RespostaProcessamento } from './api';

import LoginScreen from './components/LoginScreen';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import DashboardScreen from './components/DashboardScreen';
import ExecutionFlowScreen from './components/ExecutionFlowScreen';
import ResultScreen from './components/ResultScreen';
import CoparticipacaoResultScreen from './components/CoparticipacaoResultScreen';
import ClaroResultScreen from './components/ClaroResultScreen';
import ConfirmacaoEnvioModal from './components/ConfirmacaoEnvioModal';
import HistoryScreen from './components/HistoryScreen';
import ConfigScreen from './components/ConfigScreen';
import PerfilModal from './components/PerfilModal';
import ToastNotification from './components/ToastNotification';

/** Converte competência "AAAAMM" -> "MM/AAAA" para exibição. */
function formatarCompetencia(competencia?: string): string {
  if (!competencia || competencia.length !== 6) return competencia || '';
  return `${competencia.slice(4)}/${competencia.slice(0, 4)}`;
}

export default function App() {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  // Sem token não há sessão a restaurar: nasce já resolvido, sem esperar o efeito.
  const [restaurandoSessao, setRestaurandoSessao] = useState(() => api.getToken() !== null);

  const [activeTab, setActiveTab] = useState<ActiveTab>('dashboard');
  const [viewState, setViewState] = useState<ViewState>('list');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [perfilAberto, setPerfilAberto] = useState(false);

  // Parâmetros do fluxo
  const [selectedTipo, setSelectedTipo] = useState<string | null>(null);
  const [resultado, setResultado] = useState<RespostaProcessamento | null>(null);
  const [arquivosProcessados, setArquivosProcessados] = useState<File[]>([]);
  // Snapshot (possivelmente ajustado na tela de resultado) do fluxo de confirmação
  // único: gravar -> [enviar ao ERP -> notificar fiscal] conforme o tipo de rateio.
  const [snapshotConfirmacao, setSnapshotConfirmacao] = useState<api.Resultado | null>(null);

  // Rateio pré-filtrado ao abrir o histórico pelo botão do card. Undefined = todos
  // (é o caso do acesso pela sidebar).
  const [historicoTipo, setHistoricoTipo] = useState<string | undefined>(undefined);

  const [toasts, setToasts] = useState<Toast[]>([]);

  // Id sequencial: único na sessão, sem depender de aleatoriedade.
  const proximoToastId = useRef(0);
  const addToast = (message: string, type: Toast['type'] = 'info') => {
    const id = String(++proximoToastId.current);
    setToasts((prev) => [...prev, { id, message, type }]);
  };
  const removeToast = (id: string) => setToasts((prev) => prev.filter((t) => t.id !== id));

  // Restaura a sessão a partir do token salvo.
  useEffect(() => {
    if (!api.getToken()) return;
    api
      .me()
      .then(setUsuario)
      .catch(() => api.clearToken())
      .finally(() => setRestaurandoSessao(false));
  }, []);

  const handleLogin = (u: Usuario) => {
    setUsuario(u);
    setActiveTab('dashboard');
    setViewState('list');
    addToast(`Sessão iniciada para ${u.nome}.`, 'success');
  };

  const handleLogout = () => {
    api.clearToken();
    setUsuario(null);
    setActiveTab('dashboard');
    setViewState('list');
    setSelectedTipo(null);
    setResultado(null);
    setToasts([]);
  };

  const handleStartExecution = (tipo: string) => {
    setSelectedTipo(tipo);
    setViewState('execution-flow');
  };

  const handleProcessComplete = (resposta: RespostaProcessamento, arquivos: File[]) => {
    setResultado(resposta);
    setArquivosProcessados(arquivos);
    setViewState('result-view');
    // UM aviso só, no tom do que de fato aconteceu. Antes saíam um "sucesso"
    // verde e vários alertas âmbar ao mesmo tempo, dizendo coisas opostas; os
    // alertas em si continuam listados na própria tela de resultado.
    const alertas = resposta.alertas_validacao?.length ?? 0;
    if (alertas > 0) {
      addToast(
        `Processamento concluído com ${alertas} ponto(s) de atenção. Consulte os alertas no resultado.`,
        'warning',
      );
    } else {
      addToast('Processamento concluído.', 'success');
    }
  };

  // Reprocessa com os mesmos arquivos (ex.: após mover um colaborador para PJ).
  const handleReprocessar = async () => {
    if (!selectedTipo || arquivosProcessados.length === 0) return;
    const resposta = await api.processar(selectedTipo, arquivosProcessados);
    setResultado(resposta);
  };

  // Nem todo rateio devolve `itens` no resumo — a telefonia devolve boletos, e a
  // competência já vem formatada ("MM/AAAA") do próprio boleto.
  const competenciaAtual =
    resultado && selectedTipo === api.TIPO_CLARO
      ? api.ehResultadoClaro(resultado.resultado)
        ? (resultado.resultado.boletos[0]?.competencia ?? '')
        : ''
      : formatarCompetencia(resultado?.resultado.itens?.[0]?.competencia);

  // Abre o modal único de confirmação (gravar -> ERP -> fiscal, conforme o tipo).
  // Só aceita snapshot com `itens`: uma tela que passe `onClick={onConfirmSend}`
  // entrega o evento de clique aqui, e um snapshot inválido quebra o modal.
  // Sem snapshot válido, usa o resultado do processamento atual.
  const handleConfirmSend = (snapshot?: api.Resultado) => {
    const valido = snapshot && Array.isArray(snapshot.itens) ? snapshot : null;
    setSnapshotConfirmacao(valido ?? resultado?.resultado ?? null);
  };

  // Fecha o fluxo de confirmação. Se algo foi gravado, leva ao histórico.
  const handleFluxoClose = (gravou: boolean) => {
    setSnapshotConfirmacao(null);
    if (gravou) {
      setSelectedTipo(null);
      setResultado(null);
      setViewState('list');
      setActiveTab('historico');
    }
  };

  const handleReturnToDashboard = () => {
    setViewState('list');
    setSelectedTipo(null);
    setResultado(null);
  };

  const renderMainContent = () => {
    if (activeTab === 'historico') {
      return <HistoryScreen addToast={addToast} tipoInicial={historicoTipo} />;
    }
    if (activeTab === 'configuracoes') {
      return <ConfigScreen usuario={usuario!} addToast={addToast} />;
    }

    switch (viewState) {
      case 'execution-flow':
        return (
          <ExecutionFlowScreen
            tipo={selectedTipo!}
            onBackToDashboard={handleReturnToDashboard}
            onProcessComplete={handleProcessComplete}
            addToast={addToast}
          />
        );
      case 'result-view': {
        const propsResultado = {
          tipo: selectedTipo!,
          competence: competenciaAtual,
          resposta: resultado!,
          onBackToFlow: () => setViewState('execution-flow'),
          onConfirmSend: handleConfirmSend,
          addToast,
        };
        if (selectedTipo === api.TIPO_COPARTICIPACAO) {
          return (
            <CoparticipacaoResultScreen {...propsResultado} onReprocessar={handleReprocessar} />
          );
        }
        if (selectedTipo === api.TIPO_CLARO) {
          return <ClaroResultScreen {...propsResultado} onReprocessar={handleReprocessar} />;
        }
        return <ResultScreen {...propsResultado} onReprocessar={handleReprocessar} />;
      }
      case 'list':
      default:
        return (
          <DashboardScreen
            onStartExecution={handleStartExecution}
            onViewHistory={(tipo) => {
              setHistoricoTipo(tipo);
              setActiveTab('historico');
              setViewState('list');
            }}
            addToast={addToast}
          />
        );
    }
  };

  if (restaurandoSessao) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="h-10 w-10 border-4 border-brand-900 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!usuario) {
    return (
      <>
        <LoginScreen onLogin={handleLogin} addToast={addToast} />
        <ToastNotification toasts={toasts} removeToast={removeToast} />
      </>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 flex">
      <Sidebar
        activeTab={activeTab}
        setActiveTab={(tab) => {
          // Mantém o viewState: uma execução em andamento (result-view) sobrevive
          // ao ir para Histórico/Configurações e volta ao Dashboard como estava.
          // O filtro de rateio é do botão do card: pela sidebar, mostra todos.
          if (tab === 'historico') setHistoricoTipo(undefined);
          setActiveTab(tab);
        }}
        onLogout={handleLogout}
        onOpenPerfil={() => setPerfilAberto(true)}
        userName={usuario.nome}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
      />

      <div
        className={`flex-1 flex flex-col min-h-screen transition-[padding] duration-300 ease-in-out ${sidebarCollapsed ? 'pl-20' : 'pl-64'}`}
      >
        <Header
          activeTab={activeTab}
          viewState={viewState}
          onGoBackToDashboard={handleReturnToDashboard}
          erpAmbiente={usuario.erpAmbiente}
          rateioNome={selectedTipo ? api.nomeRateio(selectedTipo) : undefined}
        />
        <main className="flex-1 p-8 overflow-y-auto max-w-7xl w-full mx-auto">
          {renderMainContent()}
        </main>
      </div>

      {snapshotConfirmacao && selectedTipo && (
        <ConfirmacaoEnvioModal
          tipo={selectedTipo}
          competence={competenciaAtual}
          snapshot={snapshotConfirmacao}
          arquivos={arquivosProcessados}
          onClose={handleFluxoClose}
          addToast={addToast}
        />
      )}

      {perfilAberto && (
        <PerfilModal
          usuario={usuario}
          onClose={() => setPerfilAberto(false)}
          onAtualizado={(u) => setUsuario(u)}
          addToast={addToast}
        />
      )}

      <ToastNotification toasts={toasts} removeToast={removeToast} />
    </div>
  );
}
