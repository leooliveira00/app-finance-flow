import React, { useRef, useState, useEffect, type ReactNode } from 'react';
import {
  Upload,
  FileSpreadsheet,
  FileText,
  Trash2,
  ShieldAlert,
  ArrowLeft,
  Loader2,
} from 'lucide-react';
import * as api from '../api';
import { ApiError, RespostaProcessamento } from '../api';
import { Toast } from '../types';

interface ExecutionFlowScreenProps {
  tipo: string;
  onBackToDashboard: () => void;
  onProcessComplete: (resposta: RespostaProcessamento, arquivos: File[]) => void;
  addToast: (message: string, type: Toast['type']) => void;
}

// Etapas reais do processamento (backend), usadas na barra de progresso.
// Variam por tipo de rateio: a coparticipação NÃO reconcilia com NF/boleto.
function etapasDoTipo(tipo: string): string[] {
  // Telefonia não consulta o Protheus: casa por número de linha, no cadastro próprio.
  if (tipo === api.TIPO_CLARO) {
    return ['Lendo os boletos…', 'Conferindo os totais…', 'Conciliando as linhas com o cadastro…'];
  }
  const base = ['Buscando colaboradores no Protheus…', 'Lendo as planilhas…'];
  if (tipo === api.TIPO_COPARTICIPACAO) {
    return [...base, 'Calculando a coparticipação…'];
  }
  return [...base, 'Calculando o rateio…', 'Reconciliando com NF/boleto…'];
}

/** Operadora, documento de reconciliação e chave de conciliação, pelo tipo. */
function contextoOperadora(tipo: string): {
  operadora: string;
  documento: string;
  conciliacao: string;
} {
  if (tipo.includes('bradesco')) {
    return {
      operadora: 'Bradesco',
      documento: 'o boleto',
      conciliacao: 'pelo nome do titular, porque a planilha do Bradesco não traz o CPF',
    };
  }
  if (tipo.includes('unimed')) {
    return { operadora: 'Unimed', documento: 'a nota fiscal', conciliacao: 'por CPF' };
  }
  return {
    operadora: 'operadora',
    documento: 'a nota fiscal ou o boleto',
    conciliacao: 'por CPF',
  };
}

interface Orientacoes {
  /** Texto acima da área de upload. */
  instrucao: ReactNode;
  /** Extensões aceitas pelo seletor de arquivos. */
  accept: string;
  /** Legenda dentro da área de arrastar. */
  dica: string;
  /** Rótulo do botão de ação. */
  acao: string;
  /** Aviso quando o usuário tenta processar sem arquivo. */
  semArquivo: string;
  /** Itens do painel "Como funciona". */
  comoFunciona: string[];
}

/**
 * Orientações da tela de upload por tipo de rateio.
 *
 * Ficam aqui, e não num texto único, porque os processos têm entradas
 * incompatíveis: plano de saúde recebe planilha + NF e casa por CPF; telefonia
 * recebe só boletos em PDF e casa por número de linha.
 */
function orientacoesDoTipo(tipo: string): Orientacoes {
  if (tipo === api.TIPO_CLARO) {
    return {
      instrucao: (
        <>
          Envie os <strong>boletos da Claro</strong> (.pdf). Podem ser vários de uma vez. As linhas
          e os valores são lidos do próprio boleto; não há planilha nem nota fiscal.
        </>
      ),
      accept: '.pdf',
      dica: 'ou arraste os boletos (.pdf)',
      acao: 'Processar boletos',
      semArquivo: 'Carregue ao menos um boleto da Claro (PDF) para processar.',
      comoFunciona: [
        'A soma das linhas de cada boleto é conferida contra o total impresso nele.',
        'Cada linha é lançada no centro de custo do cadastro de telefonia, mantido pela TI.',
        'Cada boleto gera uma Autorização de Entrega sobre o contrato de parceria da Claro.',
      ],
    };
  }
  if (tipo === api.TIPO_COPARTICIPACAO) {
    return {
      instrucao: (
        <>
          Envie os <strong>Consolidados de coparticipação</strong> (.xlsx) da Unimed e do Bradesco.
          Não há nota fiscal: o resultado é um desconto na folha do colaborador, não um pagamento à
          operadora.
        </>
      ),
      accept: '.xlsx,.xls',
      dica: 'ou arraste os Consolidados (.xlsx)',
      acao: 'Processar coparticipação',
      semArquivo: 'Carregue ao menos um Consolidado de coparticipação (.xlsx) para processar.',
      comoFunciona: [
        'Os colaboradores vêm do Protheus, por área, e são conciliados por CPF.',
        'O valor de cada evento sai da faixa salarial do colaborador e do tipo de procedimento.',
        'No envio você informa a competência de pagamento, que é a folha em que o desconto entra.',
      ],
    };
  }
  const { operadora, documento, conciliacao } = contextoOperadora(tipo);
  return {
    instrucao: (
      <>
        Envie a <strong>planilha de valores da {operadora}</strong> (.xlsx) e, opcionalmente,{' '}
        <strong>{documento}</strong> (.pdf) para reconciliação.
      </>
    ),
    accept: '.xlsx,.xls,.pdf',
    dica: 'ou arraste os arquivos (.xlsx / .pdf)',
    acao: 'Processar rateio',
    semArquivo: 'Carregue ao menos as planilhas de valores para processar.',
    comoFunciona: [
      `Os colaboradores vêm do Protheus, por área, e são conciliados ${conciliacao}.`,
      'A planilha traz os valores por vida; cada dependente é somado no titular e rateado pelo centro de custo dele.',
      `Com ${documento} anexado, o total do rateio é conferido contra o documento antes do lançamento.`,
    ],
  };
}

function iconeArquivo(nome: string) {
  return /\.pdf$/i.test(nome) ? FileText : FileSpreadsheet;
}

function formatarTamanho(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ExecutionFlowScreen({
  tipo,
  onBackToDashboard,
  onProcessComplete,
  addToast,
}: ExecutionFlowScreenProps) {
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [processando, setProcessando] = useState(false);
  const [progresso, setProgresso] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Avança a barra suavemente até ~90% enquanto a requisição está em voo;
  // ao concluir, o handleProcessar leva a 100%.
  useEffect(() => {
    if (!processando) return;
    const id = setInterval(() => {
      setProgresso((p) => (p >= 90 ? p : p + Math.max(1, Math.round((90 - p) * 0.06))));
    }, 350);
    return () => clearInterval(id);
  }, [processando]);

  const etapas = etapasDoTipo(tipo);
  const orientacoes = orientacoesDoTipo(tipo);
  // Distribui o progresso (0–100) uniformemente entre as etapas do tipo.
  const etapaAtual = Math.min(etapas.length - 1, Math.floor(progresso / (100 / etapas.length)));

  const adicionar = (lista: FileList | null) => {
    if (!lista || lista.length === 0) return;
    const novos = Array.from(lista);
    setArquivos((prev) => {
      const nomes = new Set(prev.map((f) => f.name));
      return [...prev, ...novos.filter((f) => !nomes.has(f.name))];
    });
  };

  const remover = (nome: string) => setArquivos((prev) => prev.filter((f) => f.name !== nome));

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    adicionar(e.dataTransfer.files);
  };

  const handleProcessar = async () => {
    if (arquivos.length === 0) {
      addToast(orientacoesDoTipo(tipo).semArquivo, 'warning');
      return;
    }
    setProgresso(8);
    setProcessando(true);
    try {
      const resposta = await api.processar(tipo, arquivos);
      // Os alertas NÃO viram toast: as três telas de resultado já os listam num
      // card próprio, e disparar um toast por alerta colidia com o aviso de
      // conclusão — verde e âmbar ao mesmo tempo dizendo coisas opostas.
      // Quem resume o desfecho é `onProcessComplete`, com um aviso só.
      setProgresso(100);
      setTimeout(() => onProcessComplete(resposta, arquivos), 350);
    } catch (err) {
      if (
        err instanceof ApiError &&
        err.status === 422 &&
        err.detail &&
        typeof err.detail === 'object'
      ) {
        const d = err.detail as { erros?: string[] };
        (d.erros || ['Arquivos inválidos.']).forEach((m) => addToast(m, 'error'));
      } else if (err instanceof ApiError && err.status === 502) {
        addToast(`Erro ao consultar o Protheus: ${err.message}`, 'error');
      } else {
        addToast(err instanceof ApiError ? err.message : 'Falha no processamento.', 'error');
      }
      setProcessando(false);
    }
  };

  if (processando) {
    return (
      <div className="h-[70vh] flex flex-col items-center justify-center text-center animate-fade-in select-none">
        <div className="relative mb-8">
          <div className="absolute inset-0 rounded-full bg-brand-100 animate-ping opacity-75" />
          <div className="relative h-20 w-20 rounded-full bg-white border-4 border-brand-900 flex items-center justify-center shadow-lg">
            <Loader2 className="h-10 w-10 text-brand-900 animate-spin" />
          </div>
        </div>

        <h3 className="text-xl font-bold text-slate-900">Processando rateio…</h3>
        <p className="mt-1 mb-6 text-xs text-slate-500 max-w-md h-4">{etapas[etapaAtual]}</p>

        {/* Barra de progresso */}
        <div className="w-72 max-w-full">
          <div className="flex justify-between text-[10px] font-semibold text-slate-400 mb-1">
            <span>Progresso</span>
            <span>{progresso}%</span>
          </div>
          <div className="h-2.5 bg-slate-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-brand-900 rounded-full transition-[width] duration-300 ease-out"
              style={{ width: `${progresso}%` }}
            />
          </div>
        </div>

        {/* Etapas */}
        <div className="mt-6 flex flex-col gap-2 text-left text-xs w-72 max-w-full">
          {etapas.map((msg, i) => {
            const feito = progresso >= 100 || i < etapaAtual;
            const ativo = i === etapaAtual && progresso < 100;
            return (
              <div key={i} className="flex items-center gap-2.5">
                <div
                  className={`h-5 w-5 rounded-full flex items-center justify-center text-[10px] shrink-0 ${
                    feito
                      ? 'bg-emerald-500 text-white'
                      : ativo
                        ? 'bg-brand-900 text-white'
                        : 'bg-slate-200 text-slate-500'
                  }`}
                >
                  {feito ? '✓' : i + 1}
                </div>
                <span
                  className={
                    feito
                      ? 'text-slate-400 line-through'
                      : ativo
                        ? 'text-brand-900 font-bold'
                        : 'text-slate-400'
                  }
                >
                  {msg}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center gap-4">
        <button
          onClick={onBackToDashboard}
          className="p-2 bg-white rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-600 hover:text-slate-900 transition-colors cursor-pointer"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div>
          <h1 className="text-xl font-bold text-slate-900">{api.nomeRateio(tipo)}</h1>
          <p className="text-xs text-slate-500">Nova execução</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-sm space-y-5">
            <div className="flex items-center gap-2">
              <div className="h-6 w-6 rounded-md bg-brand-50 text-brand-800 font-bold text-xs flex items-center justify-center">
                1
              </div>
              <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wide">
                Carregar arquivos
              </h2>
            </div>
            <p className="text-xs text-slate-500">{orientacoes.instrucao}</p>

            <input
              ref={inputRef}
              type="file"
              multiple
              accept={orientacoes.accept}
              className="hidden"
              onChange={(e) => {
                adicionar(e.target.files);
                e.target.value = '';
              }}
            />

            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              onClick={() => inputRef.current?.click()}
              className={`rounded-xl border-2 border-dashed flex flex-col items-center justify-center text-center p-8 cursor-pointer transition-all ${
                dragOver
                  ? 'border-brand-600 bg-brand-50/50'
                  : 'border-slate-300 hover:border-brand-500 hover:bg-slate-50'
              }`}
            >
              <Upload className="h-8 w-8 text-slate-400 mb-2" />
              <span className="text-sm font-bold text-slate-700">Clique para selecionar</span>
              <span className="text-xs text-slate-400 mt-1">{orientacoes.dica}</span>
            </div>

            {arquivos.length > 0 && (
              <div className="space-y-2">
                {arquivos.map((f) => {
                  const Icone = iconeArquivo(f.name);
                  return (
                    <div
                      key={f.name}
                      className="p-3 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between gap-3"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="h-8 w-8 bg-brand-900 rounded-lg flex items-center justify-center shrink-0">
                          <Icone className="h-4 w-4 text-white" />
                        </div>
                        <div className="min-w-0">
                          <span className="text-xs font-bold text-slate-800 block truncate">
                            {f.name}
                          </span>
                          <span className="text-[10px] font-medium text-slate-400">
                            {formatarTamanho(f.size)}
                          </span>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => remover(f.name)}
                        className="p-1.5 hover:bg-slate-200 text-slate-500 rounded-lg transition-colors shrink-0 cursor-pointer"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}

            <hr className="border-slate-100" />

            <div className="flex items-center justify-between">
              <button
                type="button"
                onClick={onBackToDashboard}
                className="py-2.5 px-5 border border-slate-200 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer"
              >
                Cancelar
              </button>
              <button
                type="button"
                id="btn-process-rateio"
                onClick={handleProcessar}
                className={`py-2.5 px-7 rounded-xl text-xs font-bold text-white shadow-md transition-all cursor-pointer ${
                  arquivos.length > 0
                    ? 'bg-brand-900 hover:bg-brand-950'
                    : 'bg-slate-300 shadow-none cursor-not-allowed'
                }`}
                disabled={arquivos.length === 0}
              >
                {orientacoes.acao}
              </button>
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-sm space-y-4">
            <div className="flex items-center gap-2 text-brand-950">
              <ShieldAlert className="h-4.5 w-4.5 text-brand-700" />
              <h3 className="text-sm font-bold">Orientações do processo</h3>
            </div>
            <ul className="text-xs text-slate-500 space-y-2.5 list-disc pl-4 leading-relaxed">
              {orientacoes.comoFunciona.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
