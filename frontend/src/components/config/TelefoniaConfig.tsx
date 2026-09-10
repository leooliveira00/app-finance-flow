import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { Plus, Trash2, Loader2, Pencil, X, Check, Search, Smartphone, Upload } from 'lucide-react';
import * as api from '../../api';
import { ApiError, CentroCusto, LinhaTelefonica, LinhaTelefonicaIn } from '../../api';
import { Toast } from '../../types';

interface Props {
  /** Quem mantém o cadastro é a área dona do processo (TI) — não exige admin. */
  podeEditar: boolean;
  addToast: (message: string, type: Toast['type']) => void;
}

const inputCls =
  'w-full px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500';

const VAZIO: LinhaTelefonicaIn = {
  numero: '', centro_custo: '', classe_valor: '', conta: '',
  colaborador_cpf: '', colaborador_nome: '', ativo: true, observacao: '',
};

const soDigitos = (v: string) => v.replace(/\D/g, '');

/** (11) 94770 3500 — mesma grafia do boleto. */
function exibirNumero(digitos: string): string {
  const d = soDigitos(digitos);
  if (d.length < 10) return digitos;
  return `(${d.slice(0, 2)}) ${d.slice(2, -4)} ${d.slice(-4)}`;
}

/** Campos que a importação sabe preencher e os títulos aceitos no cabeçalho. */
const COLUNAS_CSV: Array<{ campo: 'numero' | 'colaborador_nome' | 'centro_custo' | 'classe_valor' | 'conta'; nomes: string[] }> = [
  { campo: 'numero', nomes: ['linha', 'numero', 'telefone', 'celular'] },
  { campo: 'colaborador_nome', nomes: ['colaborador', 'responsavel', 'usuario', 'nome'] },
  { campo: 'centro_custo', nomes: ['centro de custo', 'centro custo', 'cc'] },
  { campo: 'classe_valor', nomes: ['classe de valor', 'classe valor', 'classe', 'clvl'] },
  { campo: 'conta', nomes: ['conta', 'conta claro'] },
];
type CampoCsv = (typeof COLUNAS_CSV)[number]['campo'];

/** Ordem assumida quando o arquivo NÃO traz cabeçalho reconhecível. */
const ORDEM_PADRAO: CampoCsv[] = ['numero', 'colaborador_nome', 'centro_custo', 'classe_valor', 'conta'];

const normalizar = (s: string) =>
  s.normalize('NFD').replace(/[̀-ͯ]/g, '').trim().toLowerCase().replace(/\s+/g, ' ');

/**
 * Mapeia cada coluna do cabeçalho para o campo que ela alimenta.
 * Devolve null quando a 1ª linha não parece um cabeçalho (aí vale a ordem padrão).
 */
function mapearCabecalho(campos: string[]): Array<CampoCsv | null> | null {
  const mapa = campos.map((titulo) => {
    const t = normalizar(titulo);
    return COLUNAS_CSV.find((c) => c.nomes.includes(t))?.campo ?? null;
  });
  // Só vale como cabeçalho se reconhecer ao menos número e centro de custo.
  return mapa.includes('numero') && mapa.includes('centro_custo') ? mapa : null;
}

/**
 * Converte o CSV colado/carregado em linhas para importar.
 *
 * A ordem das colunas vem do CABEÇALHO quando ele existe — é o caso do arquivo
 * exportado pela TI, que traz a conta no meio. Assim reordenar as colunas não
 * quebra a carga, e uma coluna a mais é simplesmente ignorada.
 *
 * Separador: `;` ou tab quando presentes na linha; só então a vírgula. Assim um
 * nome com vírgula ("Souza, Ana") não parte o registro num arquivo `;`. Aspas em
 * volta do campo são removidas e o BOM que o Excel grava é descartado.
 *
 * Registro sem número, centro de custo ou classe é DESCARTADO: o backend
 * rejeitaria, e importar pela metade só criaria cadastro inválido.
 */
function lerColagem(texto: string): LinhaTelefonicaIn[] {
  const semAspas = (campo: string) => campo.trim().replace(/^"(.*)"$/, '$1').trim();
  const registros = texto
    .replace(/^﻿/, '')
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => l.split(/[;\t]/.test(l) ? /[;\t]/ : /,/).map(semAspas));
  if (registros.length === 0) return [];

  const cabecalho = mapearCabecalho(registros[0]);
  const posicoes: Array<CampoCsv | null> = cabecalho ?? ORDEM_PADRAO;
  const dados = cabecalho ? registros.slice(1) : registros;

  return dados
    .map((campos) => {
      const linha: LinhaTelefonicaIn = { ...VAZIO };
      posicoes.forEach((campo, i) => {
        const valor = campos[i];
        if (!campo || valor === undefined) return;
        linha[campo] = campo === 'numero' ? soDigitos(valor) : valor;
      });
      return linha;
    })
    .filter((l) => l.numero.length >= 10 && l.centro_custo && l.classe_valor);
}

export default function TelefoniaConfig({ podeEditar, addToast }: Props) {
  const [linhas, setLinhas] = useState<LinhaTelefonica[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [busca, setBusca] = useState('');

  const [modalAberto, setModalAberto] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<LinhaTelefonicaIn>(VAZIO);
  const [salvando, setSalvando] = useState(false);

  const [importAberto, setImportAberto] = useState(false);
  const [colagem, setColagem] = useState('');

  // Dicionário código -> nome, do cadastro de centros de custo já existente.
  // Só exibição/autocompletar: o código digitado não precisa estar nele.
  const [centros, setCentros] = useState<CentroCusto[]>([]);


  const erro = (err: unknown, fallback: string) =>
    addToast(err instanceof ApiError ? err.message : fallback, 'error');
  const recarregar = () =>
    api.listarLinhasTelefonicas().then(setLinhas).catch((e) => erro(e, 'Falha ao carregar as linhas.'));

  useEffect(() => {
    Promise.all([
      api.listarLinhasTelefonicas().then(setLinhas),
      api.listarCentrosCusto().then(setCentros),
    ])
      .catch((e) => erro(e, 'Falha ao carregar o cadastro de telefonia.'))
      .finally(() => setCarregando(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const nomePorCodigo = useMemo(
    () => new Map(centros.map((c) => [c.codigo, c.nome])),
    [centros],
  );
  const nomeCentro = (codigo: string) => nomePorCodigo.get(codigo) ?? '';



  const filtradas = useMemo(() => {
    const q = busca.trim().toLowerCase();
    if (!q) return linhas;
    const digitos = soDigitos(q);
    return linhas.filter(
      (l) =>
        (digitos && l.numero.includes(digitos)) ||
        l.centro_custo.toLowerCase().includes(q) ||
        nomeCentro(l.centro_custo).toLowerCase().includes(q) ||
        l.colaborador_nome.toLowerCase().includes(q),
    );
  }, [linhas, busca, nomePorCodigo]); // eslint-disable-line react-hooks/exhaustive-deps

  const editar = (campo: keyof LinhaTelefonicaIn, valor: string | boolean) =>
    setForm((atual) => ({ ...atual, [campo]: valor }));

  const abrirNovo = () => { setEditId(null); setForm(VAZIO); setModalAberto(true); };
  const abrirEdicao = (l: LinhaTelefonica) => {
    setEditId(l.id);
    const { id: _id, ...dados } = l;
    setForm(dados);
    setModalAberto(true);
  };
  const fechar = () => { if (!salvando) setModalAberto(false); };

  const salvar = async () => {
    const numero = soDigitos(form.numero);
    // Centro de custo e classe de valor são obrigatórios: o ERP recusa o
    // lançamento com qualquer um deles em branco.
    if (numero.length < 10 || !form.centro_custo.trim() || !form.classe_valor.trim()) {
      addToast('Informe o número com DDD, o centro de custo e a classe de valor.', 'warning');
      return;
    }
    setSalvando(true);
    try {
      const dados: LinhaTelefonicaIn = { ...form, numero, colaborador_cpf: soDigitos(form.colaborador_cpf) };
      if (editId === null) await api.criarLinhaTelefonica(dados);
      else await api.atualizarLinhaTelefonica(editId, dados);
      setModalAberto(false);
      await recarregar();
      addToast('Linha salva.', 'success');
    } catch (err) { erro(err, 'Falha ao salvar a linha.'); } finally { setSalvando(false); }
  };

  const remover = async (l: LinhaTelefonica) => {
    try {
      await api.removerLinhaTelefonica(l.id);
      await recarregar();
      addToast('Linha removida.', 'success');
    } catch (err) { erro(err, 'Falha ao remover.'); }
  };

  const importar = async () => {
    const novas = lerColagem(colagem);
    if (novas.length === 0) {
      addToast(
        'Nada reconhecido. Cada registro precisa de linha, centro de custo e classe de valor.',
        'warning',
      );
      return;
    }
    setSalvando(true);
    try {
      const { criadas, atualizadas } = await api.salvarLinhasTelefonicasEmLote(novas);
      setImportAberto(false);
      setColagem('');
      await recarregar();
      addToast(`${criadas} linha(s) criada(s) e ${atualizadas} atualizada(s).`, 'success');
    } catch (err) { erro(err, 'Falha ao importar.'); } finally { setSalvando(false); }
  };

  if (carregando) {
    return <div className="h-40 flex items-center justify-center text-slate-400"><Loader2 className="h-6 w-6 animate-spin" /></div>;
  }

  const colunas = podeEditar ? 7 : 6;

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Linhas telefônicas</h2>
          <p className="text-xs text-slate-500">
            De-para linha → centro de custo usado no lançamento das faturas da Claro. Uma linha vai
            para um único centro de custo, inclusive o excedente de uso. O responsável é informativo.
            Centro de custo e classe de valor são obrigatórios — o ERP recusa o lançamento sem eles,
            então uma linha cobrada sem os dois preenchidos bloqueia o processo.
          </p>
        </div>
        {podeEditar && (
          <div className="flex gap-2 shrink-0">
            <button onClick={() => setImportAberto(true)} className="flex items-center gap-1.5 py-2 px-4 border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-xl text-xs font-bold transition-all cursor-pointer">
              <Upload className="h-4 w-4" /> Importar
            </button>
            <button onClick={abrirNovo} className="flex items-center gap-1.5 py-2 px-4 bg-sky-600 hover:bg-sky-700 text-white rounded-xl text-xs font-bold shadow-lg shadow-sky-600/20 transition-all cursor-pointer">
              <Plus className="h-4 w-4" /> Nova linha
            </button>
          </div>
        )}
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-3 px-5 border-b border-slate-100 flex items-center gap-2">
          <Smartphone className="h-4 w-4 text-slate-500" />
          <h3 className="text-sm font-bold text-slate-900">Cadastradas</h3>
          <span className="text-[11px] font-semibold bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">{linhas.length}</span>
          <div className="ml-auto relative">
            <Search className="h-3.5 w-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar…" className="pl-8 pr-2.5 py-1.5 bg-white border border-slate-200 rounded-lg text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500 w-40" />
          </div>
        </div>
        {/* Altura FIXA (não max-height): com max-height o card encolhe conforme a
            busca filtra os registros e empurra o resto da página a cada tecla.
            Fixando, a rolagem acontece dentro do card e o layout não se move. */}
        <div className="overflow-x-auto h-[520px] overflow-y-auto">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-slate-50">
              {/* nowrap em TODOS os cabeçalhos: são rótulos curtos e fixos, e o
                  nome do centro de custo alarga a tabela o suficiente para
                  quebrá-los em duas linhas. Quem cede espaço é o conteúdo da
                  coluna Responsável, que é texto livre. */}
              <tr className="text-slate-400 font-bold border-b border-slate-100 text-[10px] uppercase tracking-wider [&>th]:whitespace-nowrap">
                <th className="py-3 px-5 w-44">Linha</th>
                <th className="py-3 px-4">Responsável</th>
                <th className="py-3 px-4">Centro de Custo</th>
                <th className="py-3 px-4">Classe de Valor</th>
                <th className="py-3 px-4">Conta</th>
                <th className="py-3 px-4">Situação</th>
                {podeEditar && <th className="py-3 px-4 w-20"></th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {filtradas.map((l) => (
                <tr key={l.id} className="hover:bg-slate-50/50">
                  <td className="py-2.5 px-5 font-mono text-slate-600 whitespace-nowrap">{exibirNumero(l.numero)}</td>
                  <td className="py-2.5 px-4 text-slate-600">{l.colaborador_nome || '—'}</td>
                  <td className="py-2.5 px-4">
                    <span className="font-medium text-slate-800">{l.centro_custo}</span>
                    {nomeCentro(l.centro_custo) && (
                      <span className="block text-[11px] text-slate-500">{nomeCentro(l.centro_custo)}</span>
                    )}
                  </td>
                  <td className="py-2.5 px-4 text-slate-500 whitespace-nowrap">{l.classe_valor || '—'}</td>
                  <td className="py-2.5 px-4 font-mono text-slate-500 whitespace-nowrap">{l.conta || '—'}</td>
                  <td className="py-2.5 px-4">
                    {l.ativo ? (
                      <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full">ativa</span>
                    ) : (
                      <span className="text-[11px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">inativa</span>
                    )}
                  </td>
                  {podeEditar && (
                    <td className="py-2.5 px-4">
                      <div className="flex gap-1">
                        <button onClick={() => abrirEdicao(l)} className="p-1.5 text-slate-400 hover:text-sky-600 hover:bg-slate-50 rounded-lg cursor-pointer" title="Editar"><Pencil className="h-4 w-4" /></button>
                        <button onClick={() => remover(l)} className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-slate-50 rounded-lg cursor-pointer" title="Remover"><Trash2 className="h-4 w-4" /></button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
              {filtradas.length === 0 && (
                <tr><td colSpan={colunas} className="py-8 text-center text-slate-400">Nenhuma linha cadastrada.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {modalAberto && createPortal(
        <div className="fixed inset-0 z-40 bg-slate-900/40 flex items-start justify-center p-4 overflow-y-auto" onClick={fechar}>
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full my-8" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-5 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900">{editId === null ? 'Nova linha' : 'Editar linha'}</h3>
              <button onClick={fechar} className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 cursor-pointer"><X className="h-4 w-4" /></button>
            </div>
            <div className="p-5 space-y-3">
              <label className="block text-[11px] font-semibold text-slate-500">Número (com DDD)
                <input value={form.numero} onChange={(e) => editar('numero', e.target.value)} placeholder="11947703500" className={`${inputCls} font-mono`} />
              </label>
              <label className="block text-[11px] font-semibold text-slate-500">Centro de Custo
                <input
                  value={form.centro_custo}
                  onChange={(e) => editar('centro_custo', e.target.value)}
                  placeholder="401070101"
                  list="centros-custo-telefonia"
                  className={`${inputCls} font-mono`}
                />
                {/* Autocompletar pelo cadastro de centros de custo, sem impedir
                    um código que ainda não esteja lá (o dicionário é só apoio). */}
                <datalist id="centros-custo-telefonia">
                  {centros.map((c) => (
                    <option key={c.id} value={c.codigo}>{c.nome}</option>
                  ))}
                </datalist>
                {nomeCentro(form.centro_custo) && (
                  <span className="block mt-1 text-[11px] font-normal text-slate-500">{nomeCentro(form.centro_custo)}</span>
                )}
              </label>
              <label className="block text-[11px] font-semibold text-slate-500">Classe de Valor
                <input value={form.classe_valor} onChange={(e) => editar('classe_valor', e.target.value)} className={inputCls} />
              </label>
              <label className="block text-[11px] font-semibold text-slate-500">Conta (opcional)
                <input value={form.conta} onChange={(e) => editar('conta', e.target.value)} placeholder="143958428" className={`${inputCls} font-mono`} />
              </label>
              <label className="block text-[11px] font-semibold text-slate-500">Responsável (opcional)
                <input value={form.colaborador_nome} onChange={(e) => editar('colaborador_nome', e.target.value)} placeholder="Nome do colaborador" className={inputCls} />
              </label>
              <label className="block text-[11px] font-semibold text-slate-500">Observação (opcional)
                <input value={form.observacao} onChange={(e) => editar('observacao', e.target.value)} className={inputCls} />
              </label>
              <label className="flex items-center gap-2 text-xs font-semibold text-slate-600 pt-1 cursor-pointer">
                <input type="checkbox" checked={form.ativo} onChange={(e) => editar('ativo', e.target.checked)} className="rounded border-slate-300" />
                Linha ativa
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

      {importAberto && createPortal(
        <div className="fixed inset-0 z-40 bg-slate-900/40 flex items-start justify-center p-4 overflow-y-auto" onClick={() => !salvando && setImportAberto(false)}>
          <div className="bg-white rounded-2xl shadow-xl max-w-lg w-full my-8" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-5 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900">Importar linhas</h3>
              <button onClick={() => setImportAberto(false)} className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 cursor-pointer"><X className="h-4 w-4" /></button>
            </div>
            <div className="p-5 space-y-3">
              <p className="text-xs text-slate-500">
                Com cabeçalho, a ordem das colunas não importa — são reconhecidos{' '}
                <span className="font-semibold">Linha, Colaborador, Centro de Custo, Classe de Valor e Conta</span>.
                Sem cabeçalho, assume-se essa mesma ordem. Linha, centro de custo e classe de valor
                são obrigatórios; número já cadastrado é atualizado. Prefira{' '}
                <span className="font-semibold">;</span> como separador — com vírgula, um nome como
                "Souza, Ana" partiria o registro.
              </p>
              <label className="flex items-center gap-2 text-xs font-semibold text-sky-700 cursor-pointer w-fit">
                <Upload className="h-3.5 w-3.5" />
                Escolher arquivo CSV
                <input
                  type="file"
                  accept=".csv,.txt,text/csv,text/plain"
                  className="hidden"
                  onChange={async (e) => {
                    const arquivo = e.target.files?.[0];
                    if (arquivo) setColagem(await arquivo.text());
                    e.target.value = ''; // permite reescolher o mesmo arquivo
                  }}
                />
              </label>
              <textarea
                value={colagem}
                onChange={(e) => setColagem(e.target.value)}
                rows={10}
                placeholder={'Linha;Colaborador;Conta;Centro de Custo;Classe de Valor\n11 96919-7936;Alexandre Pereira;143958428;301120101;3101001'}
                className={`${inputCls} font-mono text-xs`}
              />
              <p className="text-xs text-slate-400">{lerColagem(colagem).length} registro(s) reconhecido(s).</p>
            </div>
            <div className="flex justify-end gap-2 p-5 border-t border-slate-100">
              <button onClick={() => setImportAberto(false)} disabled={salvando} className="py-2 px-4 border border-slate-200 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-50 cursor-pointer disabled:opacity-50">Cancelar</button>
              <button onClick={importar} disabled={salvando} className="flex items-center gap-1.5 py-2 px-4 bg-sky-600 hover:bg-sky-700 text-white rounded-xl text-xs font-bold cursor-pointer disabled:opacity-50">
                {salvando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Importar
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
