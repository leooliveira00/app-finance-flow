import { useEffect, useMemo, useState, Fragment, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import {
  FileDown, Check, AlertTriangle, Users, Banknote, ShieldAlert,
  Info, CheckCircle2, XCircle, ChevronRight, ChevronDown, Building2, Briefcase, Loader2, MoreVertical, Search, Pencil,
} from 'lucide-react';
import * as api from '../api';
import { ApiError, RespostaProcessamento, Resultado, AgregadoResultado, ItemResultado, VidaResultado, DivergenciaResultado, CentroCusto, AjusteRateio } from '../api';
import { Toast } from '../types';
import CpfCell from './CpfCell';

/** Reagrupa o agregado a partir dos itens (mesma chave do backend: op|emp|cc|classe). */
function recomputarAgregado(itens: ItemResultado[]): AgregadoResultado[] {
  const map = new Map<string, { base: AgregadoResultado; cent: number }>();
  for (const it of itens) {
    const key = `${it.operadora}|${it.empresa}|${it.centro_custo}|${it.classe_valor}`;
    const cent = Math.round(Number(it.valor || 0) * 100);
    const g = map.get(key);
    if (g) { g.base.num_colaboradores += 1; g.cent += cent; }
    else map.set(key, { base: { operadora: it.operadora, empresa: it.empresa, centro_custo: it.centro_custo, classe_valor: it.classe_valor, num_colaboradores: 1, valor: '0' }, cent });
  }
  return [...map.values()].map((g) => ({ ...g.base, valor: (g.cent / 100).toFixed(2) }));
}

/** Aplica realocações (índice do item -> novo CC/classe) e recomputa o agregado. */
function aplicarAjustes(resultado: Resultado, ajustes: Map<number, { cc: string; classe: string }>): Resultado {
  if (ajustes.size === 0) return resultado;
  const itens = resultado.itens.map((it, i) => {
    const aj = ajustes.get(i);
    return aj ? { ...it, centro_custo: aj.cc, classe_valor: aj.classe } : it;
  });
  return { ...resultado, itens, agregado: recomputarAgregado(itens) };
}

interface ResultScreenProps {
  tipo: string;
  competence: string;
  resposta: RespostaProcessamento;
  onBackToFlow?: () => void;
  onConfirmSend?: (snapshot: Resultado) => void;
  onReprocessar?: () => Promise<void>;
  addToast: (message: string, type: Toast['type']) => void;
  // Modo leitura (consulta no histórico): esconde ações (refazer/CSV/confirmar/PJ).
  somenteLeitura?: boolean;
  /** Execução consultada no histórico: habilita a exportação lendo o snapshot
   *  gravado dela (o export do fluxo usa o último processamento em memória). */
  execucaoId?: number;
}

function moeda(valor: string | number): string {
  return Number(valor || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

/** Detalhamento das vidas/registros cobrados de um titular (titular + dependentes). */
function TabelaVidas({ vidas }: { vidas: VidaResultado[] }) {
  return (
    <table className="w-full text-[11px]">
      <tbody>
        {vidas.map((v, j) => (
          <tr key={j} className="border-b border-slate-100 last:border-0">
            <td className="py-1.5 pr-3">
              {v.titular ? (
                <span className="text-[9px] font-bold text-brand-700 bg-brand-50 border border-brand-100 px-1 py-0.5 rounded mr-1.5 align-middle">TITULAR</span>
              ) : (
                <span className="text-[9px] font-semibold text-slate-500 bg-slate-100 border border-slate-200 px-1 py-0.5 rounded mr-1.5 align-middle">Dependente</span>
              )}
              <span className="text-slate-700">{v.nome}</span>
            </td>
            <td className="py-1.5 pr-3">{v.cpf ? <CpfCell cpf={v.cpf} className="text-slate-400" /> : <span className="text-slate-300">—</span>}</td>
            <td className="py-1.5 text-right font-mono text-slate-600 whitespace-nowrap">{moeda(v.valor)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const ROTULO_DIVERGENCIA: Record<string, string> = {
  titular_nao_encontrado: 'Titular não encontrado',
  colaborador_pj: 'Colaborador PJ (sem centro de custo)',
  nome_ambiguo: 'Nome ambíguo (homônimo)',
  sem_titular: 'Família sem titular',
  atipico: 'Lançamento atípico',
};

/** Card colapsável. `defaultAberto` controla o estado inicial. */
function Secao({
  titulo, contador, defaultAberto = false, destaque = false, children,
}: {
  titulo: string;
  contador?: number;
  defaultAberto?: boolean;
  destaque?: boolean;
  children: ReactNode;
}) {
  const [aberto, setAberto] = useState(defaultAberto);
  return (
    <div className={`bg-white rounded-2xl border shadow-sm overflow-hidden ${destaque ? 'border-brand-300 ring-1 ring-brand-100' : 'border-slate-200/80'}`}>
      <div
        className="p-4 px-5 flex items-center justify-between gap-3 cursor-pointer select-none"
        onClick={() => setAberto((a) => !a)}
      >
        <div className="flex items-center gap-2 min-w-0">
          <ChevronRight className={`h-4 w-4 text-slate-400 transition-transform shrink-0 ${aberto ? 'rotate-90' : ''}`} />
          <h3 className={`text-sm font-bold truncate ${destaque ? 'text-brand-950' : 'text-slate-900'}`}>{titulo}</h3>
          {contador != null && (
            <span className="text-[11px] font-semibold bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full shrink-0">{contador}</span>
          )}
        </div>
      </div>
      {aberto && <div className="border-t border-slate-100">{children}</div>}
    </div>
  );
}

/**
 * Extrações oferecidas ao operador. Duas visões, que respondem às duas perguntas
 * do processo: como o valor foi distribuído contabilmente e quem o compõe.
 * `somenteHistorico` marca a seção que existe apenas no snapshot gravado — antes
 * da confirmação ela não foi calculada, e ofertá-la produziria download vazio.
 */
const SECOES_EXPORT: Array<{
  secao: api.SecaoExecucao;
  rotulo: string;
  ajuda: string;
  somenteHistorico?: boolean;
}> = [
  {
    secao: 'agregado',
    rotulo: 'Detalhamento por centro de custo',
    ajuda: 'Composição contábil do título lançado no ERP',
    somenteHistorico: true,
  },
  {
    secao: 'itens',
    rotulo: 'Detalhamento por colaborador',
    ajuda: 'Uma linha por titular, com vidas e valores',
  },
];

export default function ResultScreen({ tipo, competence, resposta, onBackToFlow, onConfirmSend, onReprocessar, addToast, somenteLeitura, execucaoId }: ResultScreenProps) {
  const [baixando, setBaixando] = useState(false);
  const [menuExport, setMenuExport] = useState(false);
  const [ccAbertos, setCcAbertos] = useState<Record<string, boolean>>({});
  const { total_itens, alertas_validacao, resultado: resultadoBase } = resposta;

  // Dicionário código -> nome dos centros de custo (exibição amigável + seletor).
  const [centros, setCentros] = useState<CentroCusto[]>([]);
  const [atribuindo, setAtribuindo] = useState<DivergenciaResultado | null>(null);
  const [ccSelecionado, setCcSelecionado] = useState('');
  const [buscaCc, setBuscaCc] = useState('');
  const [salvandoPJ, setSalvandoPJ] = useState(false);
  const [menuAberto, setMenuAberto] = useState<string | null>(null);
  const [filtroCc, setFiltroCc] = useState('');   // busca no card Rateio por Centro de Custo
  const [filtroDet, setFiltroDet] = useState(''); // busca no card Detalhamento por Colaborador
  // Titulares com o detalhamento de vidas expandido. Chave prefixada por quadro
  // (`cc-<idx>` / `det-<idx>`) para os dois quadros expandirem de forma independente.
  const [vidasAbertas, setVidasAbertas] = useState<Set<string>>(new Set());
  const toggleVidas = (chave: string) =>
    setVidasAbertas((s) => {
      const n = new Set(s);
      if (n.has(chave)) n.delete(chave); else n.add(chave);
      return n;
    });
  // Ajuste manual (realocação de CC/classe por colaborador) — vale só nesta execução.
  const [ajustesMap, setAjustesMap] = useState<Map<number, { cc: string; classe: string }>>(new Map());
  const [reatribuindo, setReatribuindo] = useState<number | null>(null);
  const [buscaReCc, setBuscaReCc] = useState('');

  // Resultado EXIBIDO = base + ajustes (agregado recomputado). Preserva total por empresa.
  const resultado = useMemo(() => aplicarAjustes(resultadoBase, ajustesMap), [resultadoBase, ajustesMap]);
  // Trilha de auditoria (de/para), ignorando ajustes que não mudaram nada.
  const ajustesLista = useMemo<Array<AjusteRateio & { idx: number }>>(() => {
    const lista: Array<AjusteRateio & { idx: number }> = [];
    ajustesMap.forEach((aj, i) => {
      const it = resultadoBase.itens[i];
      if (!it || (it.centro_custo === aj.cc && it.classe_valor === aj.classe)) return;
      lista.push({ idx: i, cpf: it.cpf, nome: it.nome, empresa: it.empresa, de_cc: it.centro_custo, de_classe: it.classe_valor, para_cc: aj.cc, para_classe: aj.classe, valor: it.valor });
    });
    return lista;
  }, [ajustesMap, resultadoBase]);
  const desfazerAjuste = (idx: number) =>
    setAjustesMap((prev) => { const n = new Map(prev); n.delete(idx); return n; });

  useEffect(() => {
    api.listarCentrosCusto().then(setCentros).catch(() => undefined);
  }, []);
  const nomePorCodigo = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of centros) m.set(c.codigo.trim(), c.nome);
    return m;
  }, [centros]);
  const nomeCc = (codigo: string) => nomePorCodigo.get((codigo || '').trim()) || codigo || '—';

  // Combobox de centro de custo (modal de atribuição): filtra por código ou nome.
  const centrosFiltrados = useMemo(() => {
    const q = buscaCc.trim().toLowerCase();
    const base = q
      ? centros.filter((c) => c.codigo.toLowerCase().includes(q) || c.nome.toLowerCase().includes(q))
      : centros;
    return base.slice(0, 60); // limita a lista renderizada; refine a busca para ver mais
  }, [centros, buscaCc]);

  // Atribuição de PJ: só faz sentido quando temos CPF (Unimed) e há reprocessamento.
  const ehCpf = (v: string) => /^\d{11}$/.test((v || '').replace(/\D/g, ''));
  const podeAtribuirPJ = (d: DivergenciaResultado) =>
    !!onReprocessar && (d.tipo === 'titular_nao_encontrado' || d.tipo === 'colaborador_pj') && ehCpf(d.referencia);

  const confirmarAtribuicao = async () => {
    if (!atribuindo || !ccSelecionado || !onReprocessar) return;
    const cpf = atribuindo.referencia.replace(/\D/g, '');
    const nome = atribuindo.nome;
    const empresa = atribuindo.empresa || '';
    setAtribuindo(null);
    setSalvandoPJ(true);
    try {
      await api.adicionarPJ(cpf, nome, { centro_custo: ccSelecionado, empresa });
      addToast(`${nome || cpf} atribuído a PJ. Recalculando...`, 'success');
      await onReprocessar();
      addToast('Processamento concluído.', 'success');
    } catch (err) {
      addToast(err instanceof ApiError ? err.message : 'Falha ao atribuir a PJ.', 'error');
    } finally {
      setSalvandoPJ(false);
    }
  };

  const valorRateado = resultado.totais.reduce((s, t) => s + Number(t.rateado || 0), 0);
  const totalEstornos = resultado.totais.reduce((s, t) => s + Number(t.estornos || 0), 0);
  const valorFinal = valorRateado + totalEstornos;

  const agregadoOrdenado: AgregadoResultado[] = [...resultado.agregado].sort((a, b) =>
    (a.empresa + a.centro_custo).localeCompare(b.empresa + b.centro_custo),
  );

  // Chave do agregado e agrupamento dos colaboradores para o detalhe expansível.
  const chaveCc = (x: { operadora: string; empresa: string; centro_custo: string; classe_valor: string }) =>
    `${x.operadora}|${x.empresa}|${x.centro_custo}|${x.classe_valor}`;
  const itensPorChave: Record<string, { item: ItemResultado; idx: number }[]> = {};
  resultado.itens.forEach((it, idx) => {
    (itensPorChave[chaveCc(it)] ??= []).push({ item: it, idx });
  });

  // Filtro do card "Rateio por Centro de Custo" (código / nome do CC / empresa).
  const agregadoFiltrado = useMemo(() => {
    const q = filtroCc.trim().toLowerCase();
    if (!q) return agregadoOrdenado;
    return agregadoOrdenado.filter((a) =>
      a.centro_custo.toLowerCase().includes(q) ||
      nomeCc(a.centro_custo).toLowerCase().includes(q) ||
      (a.empresa || '').toLowerCase().includes(q),
    );
  }, [agregadoOrdenado, filtroCc, nomePorCodigo]); // eslint-disable-line react-hooks/exhaustive-deps
  const subtotalFiltrado = useMemo(
    () => agregadoFiltrado.reduce((s, a) => s + Number(a.valor || 0), 0),
    [agregadoFiltrado],
  );

  // Filtro do card "Detalhamento por Colaborador" (nome / CPF / centro de custo).
  const itensFiltrados = useMemo(() => {
    const q = filtroDet.trim().toLowerCase();
    const comIdx = resultado.itens.map((item, idx) => ({ item, idx }));
    if (!q) return comIdx;
    const qd = q.replace(/\D/g, '');
    return comIdx.filter(({ item: it }) =>
      it.nome.toLowerCase().includes(q) ||
      it.centro_custo.toLowerCase().includes(q) ||
      nomeCc(it.centro_custo).toLowerCase().includes(q) ||
      (!!qd && it.cpf.replace(/\D/g, '').includes(qd)),
    );
  }, [resultado.itens, filtroDet, nomePorCodigo]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleBaixarCsv = async (secao: api.SecaoExecucao = 'itens') => {
    setBaixando(true);
    try {
      // No histórico a fonte é o snapshot da execução; no fluxo, o processamento
      // atual (que só tem os itens — as demais seções vivem no snapshot).
      if (execucaoId != null) await api.baixarCsvExecucao(execucaoId, secao);
      else await api.baixarCsv(tipo);
      addToast('Arquivo CSV gerado. O download será iniciado.', 'success');
    } catch (err) {
      addToast(err instanceof ApiError ? err.message : 'Falha ao exportar o arquivo CSV.', 'error');
    } finally {
      setBaixando(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Resultado do processamento</h1>
          <p className="text-xs text-slate-500">Competência: <strong>{competence}</strong></p>
        </div>
        {/* Exportar vale também na consulta ao histórico: analisar um processo
            passado (ex.: 041) exigia abrir o detalhe e ler na tela. */}
        <div className="flex gap-2">
          {!somenteLeitura && (
            <button
              onClick={onBackToFlow}
              className="py-2 px-4 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer"
            >
              Refazer importação
            </button>
          )}
          <div className="relative">
            <button
              onClick={() => setMenuExport((a) => !a)}
              disabled={baixando || total_itens === 0}
              className="flex items-center gap-1.5 py-2 px-4 border border-slate-200 bg-white rounded-xl text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <FileDown className="h-4 w-4 text-slate-500" />
              {baixando ? 'Gerando…' : 'Exportar'}
              <ChevronDown className={`h-3.5 w-3.5 text-slate-400 transition-transform ${menuExport ? 'rotate-180' : ''}`} />
            </button>
            {menuExport && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setMenuExport(false)} />
                <div className="absolute right-0 top-11 z-20 w-72 bg-white border border-slate-200 rounded-xl shadow-lg py-1 text-left">
                  <div className="px-3 py-1.5 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                    Extrair detalhamento (CSV)
                  </div>
                  {SECOES_EXPORT.filter((se) => execucaoId != null || !se.somenteHistorico).map((se) => (
                    /* A descrição fica no hover (title): em duas linhas, cada item
                       ficava com o dobro da altura dos demais menus da ferramenta. */
                    <button
                      key={se.secao}
                      onClick={() => { setMenuExport(false); handleBaixarCsv(se.secao); }}
                      title={se.ajuda}
                      className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 cursor-pointer"
                    >
                      <FileDown className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                      <span className="truncate">{se.rotulo}</span>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Alertas de validação */}
      {alertas_validacao.length > 0 && (
        <div className="bg-sky-50 border border-sky-200 rounded-2xl p-4 space-y-1.5">
          {alertas_validacao.map((a, i) => (
            <div key={i} className="flex items-start gap-2 text-xs text-sky-900">
              <Info className="h-4 w-4 text-sky-500 shrink-0 mt-0.5" />
              <span>{a}</span>
            </div>
          ))}
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-sm flex items-center gap-4">
          <div className="h-12 w-12 bg-brand-50 border border-brand-100 rounded-xl flex items-center justify-center shrink-0">
            <Users className="h-6 w-6 text-brand-900" />
          </div>
          <div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Colaboradores Rateados</span>
            <span className="text-2xl font-bold text-slate-900">{total_itens}</span>
          </div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-sm flex items-center gap-4">
          <div className="h-12 w-12 bg-brand-950 rounded-xl flex items-center justify-center shrink-0 shadow-sm">
            <Banknote className="h-6 w-6 text-brand-300" />
          </div>
          <div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Valor Final</span>
            <span className="text-2xl font-black text-brand-950 font-mono">{moeda(valorFinal)}</span>
            {totalEstornos !== 0 && (
              <span className="text-[10px] text-slate-500 block">
                rateado {moeda(valorRateado)} + estornos {moeda(totalEstornos)}
              </span>
            )}
          </div>
        </div>
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-sm flex items-center gap-4">
          <div className="h-12 w-12 bg-amber-50 border border-amber-100 rounded-xl flex items-center justify-center shrink-0">
            <AlertTriangle className="h-6 w-6 text-amber-500" />
          </div>
          <div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Divergências / Avisos</span>
            <span className="text-2xl font-bold text-slate-900">
              {resultado.divergencias.length} <span className="text-base text-slate-400">/ {resultado.avisos.length}</span>
            </span>
          </div>
        </div>
      </div>

      {/* DESTAQUE: Rateio por Centro de Custo (o que vai ao ERP) — aberto por padrão */}
      <Secao
        titulo="Rateio por centro de custo"
        contador={agregadoOrdenado.length}
        defaultAberto
        destaque
      >
        <div className="px-5 py-2 bg-brand-50/40 text-[11px] text-brand-800 flex items-center gap-1.5">
          <Building2 className="h-3.5 w-3.5" /> Valores consolidados por centro de custo. É a base do lançamento no ERP.
        </div>
        <div className="px-5 py-2.5 border-b border-slate-100 flex items-center gap-2">
          <div className="relative flex-1 max-w-sm">
            <Search className="h-3.5 w-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              value={filtroCc}
              onChange={(e) => setFiltroCc(e.target.value)}
              placeholder="Buscar por código, centro de custo ou empresa…"
              className="w-full pl-8 pr-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-200"
            />
          </div>
          {filtroCc.trim() !== '' && (
            <span className="text-[11px] text-slate-400 whitespace-nowrap">exibindo {agregadoFiltrado.length} de {agregadoOrdenado.length}</span>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="bg-slate-50 text-slate-400 font-bold border-y border-slate-100 text-[10px] uppercase tracking-wider">
                <th className="py-3 px-5">Empresa</th>
                <th className="py-3 px-4">Centro de custo</th>
                <th className="py-3 px-4">Classe</th>
                <th className="py-3 px-4 text-right">Colab.</th>
                <th className="py-3 px-5 text-right">Valor</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {agregadoFiltrado.map((a, i) => {
                const chave = chaveCc(a);
                const aberto = !!ccAbertos[chave];
                const filhos = itensPorChave[chave] || [];
                return (
                  <Fragment key={i}>
                    <tr
                      onClick={() => setCcAbertos((p) => ({ ...p, [chave]: !p[chave] }))}
                      className="hover:bg-slate-50/60 font-medium cursor-pointer select-none"
                      title="Clique para ver os colaboradores"
                    >
                      <td className="py-3 px-5">{a.empresa || '—'}</td>
                      <td className="py-3 px-4 font-semibold text-slate-900">
                        <span className="inline-flex items-center gap-1.5">
                          <ChevronRight className={`h-3.5 w-3.5 text-slate-400 transition-transform shrink-0 ${aberto ? 'rotate-90' : ''}`} />
                          <span>
                            <span className="font-mono text-slate-400 font-normal">{a.centro_custo}</span>
                            <span className="mx-1.5 text-slate-300">·</span>
                            {nomeCc(a.centro_custo)}
                          </span>
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono text-slate-500">{a.classe_valor}</td>
                      <td className="py-3 px-4 text-right">{a.num_colaboradores}</td>
                      <td className="py-3 px-5 text-right font-mono font-bold text-brand-950">{moeda(a.valor)}</td>
                    </tr>
                    {aberto && (
                      <tr className="bg-slate-50/40">
                        <td colSpan={5} className="px-5 py-0">
                          <div className="pl-6 py-2">
                            {filhos.length === 0 ? (
                              <div className="text-[11px] text-slate-400 py-1">Sem colaboradores neste grupo.</div>
                            ) : (
                              <table className="w-full text-[11px]">
                                <tbody>
                                  {filhos.map(({ item: f, idx }) => {
                                    // Só expande quando há mais de uma vida/registro (titular + dependentes
                                    // ou múltiplos registros). Titular sozinho não tem o que detalhar.
                                    const temVidas = (f.vidas?.length ?? 0) > 1;
                                    const chaveV = `cc-${idx}`;
                                    const vAberto = vidasAbertas.has(chaveV);
                                    return (
                                    <Fragment key={idx}>
                                    <tr className={`border-b border-slate-100 last:border-0 ${ajustesMap.has(idx) ? 'bg-amber-50/50' : ''}`}>
                                      <td className="py-1.5 pr-3 text-slate-700 font-medium">
                                        {temVidas ? (
                                          <button onClick={() => toggleVidas(chaveV)} className="inline-flex items-center gap-1 hover:text-slate-900 cursor-pointer text-left" title="Ver vidas/registros cobrados">
                                            <ChevronRight className={`h-3 w-3 text-slate-400 transition-transform shrink-0 ${vAberto ? 'rotate-90' : ''}`} />
                                            <span>{f.nome}</span>
                                          </button>
                                        ) : (
                                          <span className="inline-flex items-center gap-1">
                                            <span className="w-3 shrink-0" aria-hidden />
                                            <span>{f.nome}</span>
                                          </span>
                                        )}
                                        {f.pj && (
                                          <span className="ml-2 text-[9px] font-bold text-brand-800 bg-brand-50 border border-brand-100 px-1 py-0.5 rounded">PJ</span>
                                        )}
                                        {f.situacao && f.situacao.toUpperCase() === 'DEMITIDO' && (
                                          <span className="ml-2 text-[9px] font-bold text-rose-600 bg-rose-50 border border-rose-200 px-1 py-0.5 rounded">Demitido</span>
                                        )}
                                        {ajustesMap.has(idx) && (
                                          <span className="ml-2 text-[9px] font-bold text-amber-700 bg-amber-50 border border-amber-200 px-1 py-0.5 rounded">realocado</span>
                                        )}
                                      </td>
                                      <td className="py-1.5 pr-3"><CpfCell cpf={f.cpf} className="text-slate-400" /></td>
                                      <td className="py-1.5 pr-3 text-slate-400 whitespace-nowrap">{f.num_vidas} vida(s)</td>
                                      <td className="py-1.5 text-right font-mono font-semibold text-slate-700">{moeda(f.valor)}</td>
                                      {!somenteLeitura && (
                                        <td className="py-1.5 pl-2 text-right w-8 relative">
                                          <button
                                            onClick={() => setMenuAberto((m) => (m === `det-${idx}` ? null : `det-${idx}`))}
                                            className="p-1 rounded hover:bg-slate-200 text-slate-400 hover:text-slate-700 cursor-pointer"
                                            title="Editar"
                                          >
                                            <Pencil className="h-3 w-3" />
                                          </button>
                                          {menuAberto === `det-${idx}` && (
                                            <div className="absolute right-2 top-7 z-20 w-52 bg-white border border-slate-200 rounded-xl shadow-lg py-1 text-left">
                                              <button
                                                onClick={() => { setMenuAberto(null); setReatribuindo(idx); setBuscaReCc(''); }}
                                                className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 cursor-pointer"
                                              >
                                                <Building2 className="h-3.5 w-3.5 text-slate-400" /> Reatribuir a outro CC
                                              </button>
                                            </div>
                                          )}
                                        </td>
                                      )}
                                    </tr>
                                    {vAberto && f.vidas && (
                                      <tr>
                                        <td colSpan={somenteLeitura ? 4 : 5} className="py-0">
                                          <div className="pl-6 pb-2"><TabelaVidas vidas={f.vidas} /></div>
                                        </td>
                                      </tr>
                                    )}
                                    </Fragment>
                                    );
                                  })}
                                </tbody>
                              </table>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
              {agregadoFiltrado.length === 0 && (
                <tr><td colSpan={5} className="py-8 text-center text-slate-400">
                  {filtroCc.trim() ? 'Nenhum centro de custo encontrado para a busca.' : 'Nada a ratear.'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="bg-slate-50 p-4 px-5 border-t border-slate-100 space-y-1">
          {filtroCc.trim() !== '' && (
            <div className="flex justify-between items-baseline text-xs text-slate-500 border-b border-slate-200 pb-1.5 mb-1.5">
              <span>Exibindo {agregadoFiltrado.length} de {agregadoOrdenado.length} centros</span>
              <span>Subtotal filtrado: <span className="font-mono font-semibold text-slate-700">{moeda(subtotalFiltrado)}</span></span>
            </div>
          )}
          {totalEstornos !== 0 && (
            <>
              <div className="flex justify-end gap-3 text-xs text-slate-500">
                <span>Subtotal rateado por CC:</span>
                <span className="font-mono w-32 text-right">{moeda(valorRateado)}</span>
              </div>
              <div className="flex justify-end gap-3 text-xs text-rose-600">
                <span>Estornos (não rateados):</span>
                <span className="font-mono w-32 text-right">{moeda(totalEstornos)}</span>
              </div>
            </>
          )}
          <div className="flex justify-end gap-3 items-baseline">
            <span className="text-xs font-semibold text-slate-500">Total Final:</span>
            <span className="text-sm font-black text-brand-950 font-mono w-32 text-right">{moeda(valorFinal)}</span>
          </div>
        </div>
      </Secao>

      {/* Estornos / Créditos — negativos que só subtraem no total (sem CC) */}
      {resultado.estornos.length > 0 && (
        <Secao titulo="Estornos / Créditos (não rateados por CC)" contador={resultado.estornos.length}>
          <div className="px-5 py-2 bg-slate-50 text-[11px] text-slate-500">
            Valores negativos (ex.: exclusões retroativas). Não têm centro de custo; apenas subtraem do total final.
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="bg-slate-50 text-slate-400 font-bold border-y border-slate-100 text-[10px] uppercase tracking-wider">
                  <th className="py-3 px-5">Operadora</th>
                  <th className="py-3 px-4">Titular / Referência</th>
                  <th className="py-3 px-4 text-right">Vidas</th>
                  <th className="py-3 px-5 text-right">Valor</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {resultado.estornos.map((e, i) => (
                  <tr key={i} className="font-medium">
                    <td className="py-3 px-5 capitalize">{e.operadora}</td>
                    <td className="py-3 px-4">{e.referencia}</td>
                    <td className="py-3 px-4 text-right">{e.num_vidas}</td>
                    <td className="py-3 px-5 text-right font-mono font-bold text-rose-600">{moeda(e.valor)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Secao>
      )}

      {/* Reconciliação — colapsado */}
      {resultado.reconciliacao.length > 0 && (
        <Secao titulo="Reconciliação com NF / Boleto" contador={resultado.reconciliacao.length}>
          {/* Consistência POR EMPRESA: valor final a lançar (rateado + estornos) deve = documento. */}
          <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-3">
            {resultado.reconciliacao.map((r, i) => {
              const doc = Number(r.valor_documento || 0);
              const valorFinal = Number(r.valor_base || 0);
              const diferenca = Number(r.diferenca || 0);
              const consistente = r.bate;
              const mesma = (e: string | null) => (e || '').toUpperCase().trim() === (r.empresa || '').toUpperCase().trim();
              const rateadoEmp = resultado.itens.filter((it) => mesma(it.empresa)).reduce((s, it) => s + Number(it.valor || 0), 0);
              const estornoEmp = resultado.estornos.filter((e) => mesma(e.empresa)).reduce((s, e) => s + Number(e.valor || 0), 0);
              const divsEmp = resultado.divergencias.filter((d) => mesma(d.empresa));
              const somaDiv = divsEmp.reduce((s, d) => s + Number(d.valor || 0), 0);
              const naoExplicado = diferenca - somaDiv;
              return (
                <div key={i} className={`rounded-xl border p-4 ${consistente ? 'border-emerald-200 bg-emerald-50/40' : 'border-rose-200 bg-rose-50/40'}`}>
                  <div className="flex items-center gap-2 mb-3">
                    {consistente ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : <XCircle className="h-4 w-4 text-rose-500" />}
                    <span className="text-sm font-bold text-slate-900">{r.empresa || '(empresa não identificada)'}</span>
                    <span className="text-[10px] text-slate-400 capitalize">· {r.operadora} · {r.operadora === 'unimed' ? 'NF' : 'boleto'}</span>
                    <span className={`ml-auto text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded border ${consistente ? 'bg-emerald-100 text-emerald-700 border-emerald-200' : 'bg-rose-100 text-rose-700 border-rose-200'}`}>
                      {consistente ? 'Consistente' : 'Inconsistência'}
                    </span>
                  </div>
                  <div className="text-xs font-mono space-y-1 max-w-md">
                    <div className="flex justify-between"><span className="text-slate-600">Documento (NF/boleto)</span><span className="font-semibold">{moeda(doc)}</span></div>
                    <div className="flex justify-between"><span className="text-slate-600">Valor final a lançar</span><span className="font-semibold">{moeda(valorFinal)}</span></div>
                    <div className="flex justify-between text-[11px] text-slate-400"><span className="pl-3">rateado {moeda(rateadoEmp)} · estornos {moeda(estornoEmp)}</span><span /></div>
                    <div className={`flex justify-between border-t border-slate-200 pt-1 font-bold ${consistente ? 'text-emerald-700' : 'text-rose-700'}`}>
                      <span>Diferença (documento − final)</span><span>{moeda(diferenca)}</span>
                    </div>
                    {!consistente && (
                      <div className="pt-1 pl-3 text-[11px] text-slate-500 space-y-0.5">
                        <div className="flex justify-between"><span>├ Divergências não rateadas ({divsEmp.length})</span><span>{moeda(somaDiv)}</span></div>
                        <div className="flex justify-between"><span>└ Não explicado (extração/arquivo)</span><span>{moeda(naoExplicado)}</span></div>
                      </div>
                    )}
                  </div>
                  <p className="text-[11px] mt-2 leading-relaxed text-slate-500">
                    {consistente
                      ? 'O valor final a lançar (com estornos já abatidos) confere com o documento desta empresa.'
                      : 'O valor a lançar difere do documento. Resolva as divergências desta empresa. "Não explicado" indica erro de extração ou arquivo do período/empresa errado.'}
                  </p>
                </div>
              );
            })}
          </div>
        </Secao>
      )}

      {/* Avisos — colapsado */}
      {resultado.avisos.length > 0 && (
        <Secao titulo="Avisos" contador={resultado.avisos.length}>
          <div className="p-4 space-y-2">
            {resultado.avisos.map((a, i) => (
              <div key={i} className="bg-amber-50 border border-amber-200/60 p-3 rounded-xl text-xs text-amber-900 font-medium leading-relaxed">{a}</div>
            ))}
          </div>
        </Secao>
      )}

      {/* Divergências — colapsado */}
      {resultado.divergencias.length > 0 && (
        <Secao titulo="Divergências" contador={resultado.divergencias.length}>
          <div className="p-4 flex flex-col gap-2">
            {resultado.divergencias.map((d, i) => (
              <div key={i} className="border border-slate-200 p-3 rounded-xl flex items-start justify-between gap-3">
                <div className="flex items-start gap-2.5 min-w-0">
                  <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200 shrink-0">
                    {ROTULO_DIVERGENCIA[d.tipo] || d.tipo}
                  </span>
                  <div className="min-w-0">
                    {d.nome && <span className="text-xs font-bold text-slate-900 block">{d.nome}</span>}
                    <span className="text-xs text-slate-600 leading-relaxed">{d.descricao}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs font-mono font-semibold text-slate-500">{moeda(d.valor)}</span>
                  {podeAtribuirPJ(d) && (
                    <div className="relative">
                      <button
                        onClick={() => setMenuAberto((m) => (m === `div-${i}` ? null : `div-${i}`))}
                        className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-700 cursor-pointer"
                        title="Ações"
                      >
                        <MoreVertical className="h-4 w-4" />
                      </button>
                      {menuAberto === `div-${i}` && (
                        <div className="absolute right-0 top-8 z-20 w-44 bg-white border border-slate-200 rounded-xl shadow-lg py-1 text-left">
                          <button
                            onClick={() => { setMenuAberto(null); setAtribuindo(d); setCcSelecionado(''); setBuscaCc(''); }}
                            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 cursor-pointer"
                            title="Atribuir a PJ e escolher o centro de custo"
                          >
                            <Briefcase className="h-3.5 w-3.5 text-slate-400" /> Atribuir a PJ
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Secao>
      )}

      {/* Detalhamento por colaborador — colapsado, com copiar */}
      <Secao titulo="Detalhamento por Colaborador" contador={total_itens}>
        <div className="px-5 py-2.5 border-b border-slate-100 flex items-center gap-2">
          <div className="relative flex-1 max-w-sm">
            <Search className="h-3.5 w-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              value={filtroDet}
              onChange={(e) => setFiltroDet(e.target.value)}
              placeholder="Buscar por nome, CPF ou centro de custo…"
              className="w-full pl-8 pr-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-200"
            />
          </div>
          {filtroDet.trim() !== '' && (
            <span className="text-[11px] text-slate-400 whitespace-nowrap">exibindo {itensFiltrados.length} de {resultado.itens.length}</span>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="bg-slate-50 text-slate-400 font-bold border-b border-slate-100 text-[10px] uppercase tracking-wider">
                <th className="py-3 px-5">Nome</th>
                <th className="py-3 px-4">CPF</th>
                <th className="py-3 px-4">Empresa</th>
                <th className="py-3 px-4">Centro de custo</th>
                <th className="py-3 px-5 text-right">Valor</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {itensFiltrados.map(({ item, idx }) => {
                // Só expande com mais de uma vida/registro (titular + dependentes ou
                // múltiplos registros). Titular sozinho não tem detalhamento a abrir.
                const temVidas = (item.vidas?.length ?? 0) > 1;
                const chaveV = `det-${idx}`;
                const vAberto = vidasAbertas.has(chaveV);
                return (
                <Fragment key={`${item.cpf}-${item.operadora}-${idx}`}>
                <tr className={`hover:bg-slate-50/50 font-medium ${ajustesMap.has(idx) ? 'bg-amber-50/40' : ''}`}>
                  <td className="py-3 px-5 font-semibold text-slate-900">
                    {temVidas ? (
                      <button onClick={() => toggleVidas(chaveV)} className="inline-flex items-center gap-1.5 hover:text-brand-900 cursor-pointer text-left" title="Ver vidas/registros cobrados">
                        <ChevronRight className={`h-3.5 w-3.5 text-slate-400 transition-transform shrink-0 ${vAberto ? 'rotate-90' : ''}`} />
                        <span>{item.nome}</span>
                      </button>
                    ) : (
                      <span className="inline-flex items-center gap-1.5">
                        <span className="w-3.5 shrink-0" aria-hidden />
                        <span>{item.nome}</span>
                      </span>
                    )}
                    {item.pj && (
                      <span className="ml-2 text-[10px] font-bold text-brand-800 bg-brand-50 border border-brand-100 px-1.5 py-0.5 rounded">PJ</span>
                    )}
                    {item.situacao && item.situacao.toUpperCase() === 'DEMITIDO' && (
                      <span className="ml-2 text-[10px] font-bold text-rose-600 bg-rose-50 border border-rose-200 px-1.5 py-0.5 rounded">Demitido</span>
                    )}
                    {ajustesMap.has(idx) && (
                      <span className="ml-2 text-[10px] font-bold text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded">realocado</span>
                    )}
                  </td>
                  <td className="py-3 px-4"><CpfCell cpf={item.cpf} /></td>
                  <td className="py-3 px-4">{item.empresa}</td>
                  <td className="py-3 px-4">
                    {nomeCc(item.centro_custo)}
                    <span className="block text-[10px] font-mono text-slate-400">{item.centro_custo}</span>
                  </td>
                  <td className="py-3 px-5 text-right font-mono font-bold text-slate-900">{moeda(item.valor)}</td>
                </tr>
                {vAberto && item.vidas && (
                  <tr className="bg-slate-50/40">
                    <td colSpan={5} className="px-5 py-0">
                      <div className="pl-6 py-2 max-w-2xl"><TabelaVidas vidas={item.vidas} /></div>
                    </td>
                  </tr>
                )}
                </Fragment>
                );
              })}
              {itensFiltrados.length === 0 && (
                <tr><td colSpan={5} className="py-8 text-center text-slate-400">
                  {filtroDet.trim() ? 'Nenhum colaborador encontrado para a busca.' : 'Nenhum colaborador rateado (verifique as divergências).'}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Secao>

      {/* Auditoria: realocações manuais de centro de custo (perto da confirmação) */}
      {ajustesLista.length > 0 && (
        <div className="bg-white rounded-2xl border border-amber-200 shadow-sm overflow-hidden">
          <div className="px-5 py-3 bg-amber-50 border-b border-amber-100 flex items-center gap-2">
            <Pencil className="h-4 w-4 text-amber-500 shrink-0" />
            <span className="text-sm font-bold text-amber-900">Realocações manuais</span>
            <span className="text-[11px] font-semibold bg-amber-100 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full">{ajustesLista.length}</span>
            <span className="ml-auto text-[11px] text-amber-700">total por empresa preservado</span>
          </div>
          <div className="divide-y divide-slate-100">
            {ajustesLista.map((a) => (
              <div key={a.idx} className="px-5 py-2.5 flex items-center gap-3 text-xs">
                <div className="min-w-0 flex-1">
                  <div>
                    <span className="font-semibold text-slate-900">{a.nome}</span>
                    <span className="text-slate-400"> · {a.empresa}</span>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-0.5 flex items-center gap-1.5 flex-wrap">
                    <span className="font-mono">{a.de_cc}</span>
                    <span className="text-slate-400">{nomeCc(a.de_cc)}</span>
                    <span className="text-slate-300">→</span>
                    <span className="font-mono font-semibold text-slate-700">{a.para_cc}</span>
                    <span className="text-slate-600">{nomeCc(a.para_cc)}</span>
                  </div>
                </div>
                <span className="font-mono font-semibold text-slate-700 shrink-0">{moeda(a.valor)}</span>
                {!somenteLeitura && (
                  <button
                    onClick={() => desfazerAjuste(a.idx)}
                    className="shrink-0 text-[11px] font-semibold text-slate-500 hover:text-rose-600 border border-slate-200 rounded-lg px-2 py-1 hover:bg-slate-50 cursor-pointer"
                  >
                    desfazer
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Confirmação FLUTUANTE no canto inferior direito: com os quadros de
          detalhamento abertos a página fica longa, e o botão no fim exigia rolar
          todos os registros para chegar à ação. */}
      {!somenteLeitura && createPortal(
        <div className="fixed bottom-6 right-6 z-40">
          <button
            onClick={() => onConfirmSend?.({ ...resultado, ajustes: ajustesLista.map(({ idx, ...a }) => a) })}
            id="btn-confirm-protheus-trigger"
            disabled={total_itens === 0}
            title="Revise divergências e reconciliação antes de confirmar. Grava a execução no histórico e gera os títulos no ERP."
            className="flex items-center gap-2 py-3 px-6 bg-emerald-600 hover:bg-emerald-700 text-white rounded-2xl text-xs font-bold shadow-xl shadow-emerald-950/20 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Check className="h-4 w-4" />
            Confirmar resultado
          </button>
        </div>,
        document.body,
      )}

      {/* Fecha o menu ao clicar fora */}
      {menuAberto && <div className="fixed inset-0 z-10" onClick={() => setMenuAberto(null)} />}

      {/* Modal: atribuir divergência a PJ + escolher centro de custo */}
      {atribuindo && createPortal(
        <div className="fixed inset-0 z-30 bg-slate-900/40 flex items-center justify-center p-4" onClick={() => setAtribuindo(null)}>
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start gap-3">
              <div className="h-10 w-10 rounded-xl bg-brand-50 border border-brand-100 flex items-center justify-center shrink-0">
                <Briefcase className="h-5 w-5 text-brand-900" />
              </div>
              <div className="min-w-0">
                <h3 className="text-sm font-bold text-slate-900">Atribuir a PJ</h3>
                <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                  <strong className="text-slate-700">{atribuindo.nome || atribuindo.referencia}</strong> será cadastrado como PJ e rateado ao centro de custo escolhido
                  {atribuindo.empresa ? <> (empresa <strong>{atribuindo.empresa}</strong>)</> : null}. Passa a valer também nas próximas execuções.
                </p>
              </div>
            </div>
            <div className="mt-4">
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1">Centro de custo</label>
              <div className="relative">
                <Search className="h-4 w-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  autoFocus
                  value={buscaCc}
                  onChange={(e) => setBuscaCc(e.target.value)}
                  placeholder="Buscar por código ou nome…"
                  className="w-full pl-9 pr-3 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-200"
                />
              </div>
              <div className="mt-2 border border-slate-200 rounded-lg max-h-60 overflow-y-auto divide-y divide-slate-100">
                {centrosFiltrados.map((c) => {
                  const sel = c.codigo === ccSelecionado;
                  return (
                    <button
                      key={c.id}
                      onClick={() => setCcSelecionado(c.codigo)}
                      className={`w-full flex items-center gap-2 px-3 py-2 text-left cursor-pointer transition-colors ${sel ? 'bg-brand-50' : 'hover:bg-slate-50'}`}
                    >
                      <span className={`h-4 w-4 rounded-full border flex items-center justify-center shrink-0 ${sel ? 'bg-brand-900 border-brand-900' : 'border-slate-300'}`}>
                        {sel && <Check className="h-2.5 w-2.5 text-white" />}
                      </span>
                      <span className="min-w-0">
                        <span className="block text-sm text-slate-800 truncate">{c.nome || '—'}</span>
                        <span className="block text-[10px] font-mono text-slate-400">{c.codigo}</span>
                      </span>
                    </button>
                  );
                })}
                {centros.length === 0 && (
                  <p className="text-[11px] text-amber-600 p-3">Nenhum centro de custo cadastrado. Cadastre em Configurações ▸ Centros de custo.</p>
                )}
                {centros.length > 0 && centrosFiltrados.length === 0 && (
                  <p className="text-xs text-slate-400 p-3 text-center">Nenhum centro de custo encontrado.</p>
                )}
              </div>
              {buscaCc.trim() === '' && centros.length > centrosFiltrados.length && (
                <p className="text-[10px] text-slate-400 mt-1">Mostrando {centrosFiltrados.length} de {centros.length}. Digite para refinar.</p>
              )}
            </div>
            <div className="mt-5 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
              <button onClick={() => setAtribuindo(null)} className="py-2 px-4 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 cursor-pointer">
                Cancelar
              </button>
              <button onClick={confirmarAtribuicao} disabled={!ccSelecionado} className="py-2 px-4 bg-brand-900 hover:bg-brand-950 text-white rounded-xl text-xs font-bold cursor-pointer disabled:opacity-50">
                Atribuir e reprocessar
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}

      {/* Overlay de reprocessamento */}
      {salvandoPJ && createPortal(
        <div className="fixed inset-0 z-40 bg-slate-900/30 flex items-center justify-center">
          <div className="bg-white rounded-2xl shadow-xl px-6 py-4 flex items-center gap-3">
            <Loader2 className="h-5 w-5 animate-spin text-brand-900" />
            <span className="text-sm font-semibold text-slate-700">Reprocessando…</span>
          </div>
        </div>,
        document.body,
      )}

      {/* Modal: reatribuir um colaborador a outro centro de custo */}
      {reatribuindo !== null && resultadoBase.itens[reatribuindo] && createPortal(
        (() => {
          const item = resultadoBase.itens[reatribuindo];
          const q = buscaReCc.trim().toLowerCase();
          const lista = (q ? centros.filter((c) => c.codigo.toLowerCase().includes(q) || c.nome.toLowerCase().includes(q)) : centros).slice(0, 60);
          const escolher = (codigo: string) => {
            setAjustesMap((prev) => { const n = new Map(prev); n.set(reatribuindo, { cc: codigo, classe: item.classe_valor }); return n; });
            setReatribuindo(null);
          };
          return (
            <div className="fixed inset-0 z-30 bg-slate-900/40 flex items-center justify-center p-4" onClick={() => setReatribuindo(null)}>
              <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-5" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-start gap-3">
                  <div className="h-10 w-10 rounded-xl bg-brand-50 border border-brand-100 flex items-center justify-center shrink-0">
                    <Building2 className="h-5 w-5 text-brand-900" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-sm font-bold text-slate-900">Reatribuir centro de custo</h3>
                    <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                      <strong className="text-slate-700">{item.nome}</strong> · {item.empresa} · {moeda(item.valor)}. Atual: <strong>{nomeCc(item.centro_custo)}</strong> ({item.centro_custo}). O valor migra para o CC escolhido; o total da empresa não muda.
                    </p>
                  </div>
                </div>
                <div className="mt-4">
                  <div className="relative">
                    <Search className="h-4 w-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                    <input autoFocus value={buscaReCc} onChange={(e) => setBuscaReCc(e.target.value)} placeholder="Buscar por código ou nome…" className="w-full pl-9 pr-3 py-2 bg-white border border-slate-200 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-200" />
                  </div>
                  <div className="mt-2 border border-slate-200 rounded-lg max-h-60 overflow-y-auto divide-y divide-slate-100">
                    {lista.map((c) => (
                      <button key={c.id} onClick={() => escolher(c.codigo)} className={`w-full flex items-center justify-between gap-2 px-3 py-2 text-left cursor-pointer hover:bg-slate-50 ${c.codigo === item.centro_custo ? 'bg-slate-50' : ''}`}>
                        <span className="min-w-0"><span className="block text-sm text-slate-800 truncate">{c.nome || '—'}</span><span className="block text-[10px] font-mono text-slate-400">{c.codigo}</span></span>
                      </button>
                    ))}
                    {centros.length === 0 && <p className="text-[11px] text-amber-600 p-3">Nenhum centro de custo cadastrado.</p>}
                    {centros.length > 0 && lista.length === 0 && <p className="text-xs text-slate-400 p-3 text-center">Nenhum encontrado.</p>}
                  </div>
                </div>
                <div className="mt-4 flex justify-end">
                  <button onClick={() => setReatribuindo(null)} className="py-2 px-4 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 cursor-pointer">Cancelar</button>
                </div>
              </div>
            </div>
          );
        })(),
        document.body,
      )}
    </div>
  );
}
