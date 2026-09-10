"""
Cálculo do rateio do Pagamento do Plano de Saúde.

Responsabilidade (regra de negócio pura — sem arquivo, sem API, sem banco):
a partir das planilhas já normalizadas pelo `parser` e da lista de
colaboradores vinda da API (injetada em `dados_externos`), agrega o valor de
cada família (titular + dependentes) e atribui ao centro de custo do titular.

Casamento planilha × API (apenas pelo TITULAR — decisão de negócio):
- UNIMED: pelo CPF do titular (`grupo_familiar`).
- BRADESCO: pelo NOME do titular normalizado (não há CPF na planilha).

Fonte da verdade dos dados contábeis é a API: `empresa`, `centro_custo`,
`classe_valor` e `matricula` saem do colaborador da API, não da planilha.

Saída (`ResultadoRateio`):
- `itens`: uma linha por colaborador × operadora (detalhe).
- `agregado`: soma por (operadora, empresa, centro_custo, classe_valor),
  pronta para o lançamento no ERP.
- `divergencias`: titular não encontrado, nome ambíguo (Bradesco), família sem
  titular e as linhas atípicas do parser — tudo que precisa de tratativa.
- `totais`: subtotais por operadora (e por operadora×empresa) para a
  reconciliação com NF/boleto no passo de validators.

Cuidados: tudo em `Decimal`; valores negativos (estornos) são preservados e
reduzem o total do colaborador/centro de custo normalmente.
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from .parser import LinhaValor, PlanilhaValores, normalizar_cpf

if TYPE_CHECKING:  # evita import circular (validators importa este módulo)
    from .validators import AlertaReconciliacao

# Chave em dados_externos com a lista de colaboradores da API.
CHAVE_COLABORADORES = "colaboradores"

# Situações inativas (colaborador desligado). Comparadas normalizadas.
SITUACOES_INATIVAS = {"DEMITIDO"}


# ---------------------------------------------------------------------------
# Estruturas de saída
# ---------------------------------------------------------------------------
@dataclass
class ItemColaborador:
    """Detalhe do rateio de um colaborador em uma operadora."""

    operadora: str
    competencia: str
    empresa: str
    cpf: str
    nome: str
    centro_custo: str
    classe_valor: str
    matricula: str
    num_vidas: int
    valor: Decimal
    situacao: str = ""   # situação do colaborador na API (ex.: "Demitido")
    pj: bool = False     # colaborador PJ (não veio da API; centro de custo atribuído)
    # Detalhamento por vida/registro cobrado (titular + dependentes) que compõem
    # o valor agregado — para a UI expandir o titular. Cada item: nome/cpf/valor/titular.
    vidas: list[dict] = field(default_factory=list)


@dataclass
class ItemAgregado:
    """Soma por (operadora, empresa, centro_custo, classe_valor) para o ERP."""

    operadora: str
    empresa: str
    centro_custo: str
    classe_valor: str
    num_colaboradores: int
    valor: Decimal


@dataclass
class Divergencia:
    """Item que não pôde ser rateado e precisa de tratativa do usuário."""

    tipo: str            # titular_nao_encontrado | nome_ambiguo | sem_titular | atipico
    operadora: str
    referencia: str      # CPF, nome do titular ou certificado (uso interno)
    descricao: str
    valor: Decimal
    num_vidas: int = 0
    nome: str = ""       # nome completo do titular (exibido na UI)
    empresa: str = ""    # empresa de faturamento (NOME_EMPRESA da planilha), se houver


@dataclass
class Estorno:
    """
    Registro com valor NEGATIVO (estorno / crédito, ex.: exclusão retroativa).

    Regra de negócio: colaboradores com valor negativo NÃO são consultados na
    API (evita divergência falsa de "não encontrado" para quem já saiu) — o
    valor apenas SUBTRAI no total final. Não é rateado por centro de custo.
    """

    operadora: str
    referencia: str    # nome do titular ou grupo familiar
    valor: Decimal     # negativo
    num_vidas: int = 0
    empresa: str = ""  # NOME_EMPRESA da planilha (p/ compor o valor final por empresa)


@dataclass
class TotaisOperadora:
    """Subtotais de uma operadora para a reconciliação com NF/boleto."""

    operadora: str
    rateado: Decimal        # soma dos itens casados (positivos)
    estornos: Decimal       # soma dos registros negativos (não consultados na API)
    nao_rateado: Decimal    # divergências (não encontrados, ambíguos, atípicos)
    total: Decimal          # rateado + estornos + nao_rateado (= faturado na planilha)


@dataclass
class ResultadoRateio:
    itens: list[ItemColaborador] = field(default_factory=list)
    agregado: list[ItemAgregado] = field(default_factory=list)
    divergencias: list[Divergencia] = field(default_factory=list)
    estornos: list[Estorno] = field(default_factory=list)
    totais: list[TotaisOperadora] = field(default_factory=list)
    # Avisos informativos (não afetam a reconciliação): ex.: demitido rateado.
    avisos: list[str] = field(default_factory=list)
    # Matched por (operadora, empresa) — reconciliação por NF/boleto específico.
    totais_por_operadora_empresa: dict[tuple[str, str], Decimal] = field(
        default_factory=dict
    )
    # Soma de VALOR TOTAL da PLANILHA por empresa (NOME_EMPRESA normalizado);
    # "" = sem empresa na planilha (ex.: Bradesco, atípicas). Base para reconciliar
    # com a NF/boleto — inclui TUDO (positivos e negativos), como a NF.
    total_faturado_por_empresa: dict[str, Decimal] = field(default_factory=dict)
    # Preenchido pelo module após comparar com NF/boleto (validators.reconciliar).
    reconciliacao: list[AlertaReconciliacao] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Índices da API
# ---------------------------------------------------------------------------
def _normalizar_nome(valor: Any) -> str:
    if valor is None:
        return ""
    forma = unicodedata.normalize("NFKD", str(valor)).upper()
    sem_acento = "".join(c for c in forma if not unicodedata.combining(c))
    return " ".join(sem_acento.split())


def _colaborador_ativo(colaborador: dict) -> bool:
    return _normalizar_nome(colaborador.get("situacao")) not in SITUACOES_INATIVAS


@dataclass
class _IndicesColaboradores:
    por_cpf: dict[str, dict]
    por_nome: dict[str, list[dict]]


def _indexar_colaboradores(colaboradores: list[dict]) -> _IndicesColaboradores:
    por_cpf: dict[str, dict] = {}
    por_nome: dict[str, list[dict]] = defaultdict(list)
    for colab in colaboradores:
        cpf = normalizar_cpf(colab.get("cpf"))
        if cpf:
            por_cpf.setdefault(cpf, colab)
        nome = _normalizar_nome(colab.get("nome"))
        if nome:
            por_nome[nome].append(colab)
    return _IndicesColaboradores(por_cpf=por_cpf, por_nome=dict(por_nome))


# ---------------------------------------------------------------------------
# Agrupamento por família
# ---------------------------------------------------------------------------
@dataclass
class _Familia:
    operadora: str
    grupo_familiar: str
    competencia: str
    linhas: list[LinhaValor]

    @property
    def valor_total(self) -> Decimal:
        return sum((l.valor for l in self.linhas), Decimal("0"))

    @property
    def num_vidas(self) -> int:
        return len(self.linhas)

    @property
    def titular(self) -> LinhaValor | None:
        for linha in self.linhas:
            if linha.is_titular:
                return linha
        return None

    @property
    def nome_titular(self) -> str:
        tit = self.titular
        if tit and tit.nome_titular:
            return tit.nome_titular
        if tit:
            return tit.nome
        # Fallback: qualquer nome_titular presente nas linhas.
        for linha in self.linhas:
            if linha.nome_titular:
                return linha.nome_titular
        return ""

    @property
    def empresa_planilha(self) -> str | None:
        """Empresa de faturamento (NOME_EMPRESA), quando a planilha traz (Unimed)."""
        for linha in self.linhas:
            if linha.empresa_planilha:
                return linha.empresa_planilha
        return None


def _agrupar_familias(planilhas: list[PlanilhaValores]) -> list[_Familia]:
    grupos: dict[tuple[str, str], _Familia] = {}
    for planilha in planilhas:
        for linha in planilha.linhas:
            chave = (linha.operadora, linha.grupo_familiar)
            familia = grupos.get(chave)
            if familia is None:
                familia = _Familia(
                    operadora=linha.operadora,
                    grupo_familiar=linha.grupo_familiar,
                    competencia=linha.competencia,
                    linhas=[],
                )
                grupos[chave] = familia
            familia.linhas.append(linha)
    return list(grupos.values())


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------
def _resolver_pj(
    cpf: str, familia: _Familia, pj: dict
) -> tuple[dict | None, Divergencia | None]:
    """
    Trata um titular que NÃO está na API mas está no cadastro PJ.

    Com centro de custo atribuído -> vira um "colaborador" sintético (rateado,
    marcado como PJ). Sem centro de custo -> divergência informativa para o
    operador atribuir um centro de custo na tela de resultado.
    """
    if not (pj.get("centro_custo") or "").strip():
        return None, Divergencia(
            tipo="colaborador_pj",
            operadora=familia.operadora,
            referencia=cpf,
            nome=familia.nome_titular or str(pj.get("nome", "")),
            descricao="Colaborador PJ sem centro de custo — atribua um centro de custo para ratear.",
            valor=familia.valor_total,
            num_vidas=familia.num_vidas,
            empresa=familia.empresa_planilha or str(pj.get("empresa", "")),
        )
    return {
        "cpf": cpf,
        "nome": familia.nome_titular or str(pj.get("nome", "")),
        "centro_custo": str(pj.get("centro_custo", "")),
        "empresa": str(pj.get("empresa", "")),
        "classe_valor": str(pj.get("classe_valor", "")),
        "matricula": "",
        "situacao": "PJ",
        "_pj": True,
    }, None


def _casar_familia(
    familia: _Familia,
    indices: _IndicesColaboradores,
    pj_por_cpf: dict[str, dict],
    pj_por_nome: dict[str, dict],
) -> tuple[dict | None, Divergencia | None]:
    """Encontra o colaborador da API para a família, ou devolve a divergência."""
    if familia.operadora == "unimed":
        # Unimed casa pelo CPF do titular (grupo_familiar), presente em toda linha
        # — inclusive quando o titular não tem linha própria (ex.: coparticipação
        # de dependente sem uso do titular no mês). Só falta CPF -> sem_titular.
        cpf = familia.grupo_familiar  # já normalizado no parser
        if not cpf:
            return None, Divergencia(
                tipo="sem_titular",
                operadora="unimed",
                referencia="",
                descricao="Família sem CPF de titular identificável.",
                valor=familia.valor_total,
                num_vidas=familia.num_vidas,
                empresa=familia.empresa_planilha or "",
            )
        colab = indices.por_cpf.get(cpf)
        if colab is None:
            pj = pj_por_cpf.get(cpf)
            if pj is not None:
                return _resolver_pj(cpf, familia, pj)
            return None, Divergencia(
                tipo="titular_nao_encontrado",
                operadora="unimed",
                referencia=cpf,
                nome=familia.nome_titular,
                descricao="Titular não encontrado na API.",
                valor=familia.valor_total,
                num_vidas=familia.num_vidas,
                empresa=familia.empresa_planilha or "",
            )
        return colab, None

    # bradesco: casa por NOME do titular — exige uma linha/nome de titular.
    if familia.titular is None and not familia.nome_titular:
        return None, Divergencia(
            tipo="sem_titular",
            operadora="bradesco",
            referencia=familia.grupo_familiar,
            descricao="Família sem linha de titular identificável.",
            valor=familia.valor_total,
            num_vidas=familia.num_vidas,
            empresa=familia.empresa_planilha or "",
        )
    nome = _normalizar_nome(familia.nome_titular)
    candidatos = indices.por_nome.get(nome, [])
    if not candidatos:
        pj = pj_por_nome.get(nome)
        if pj is not None:
            return _resolver_pj(str(pj.get("cpf", "")), familia, pj)
        return None, Divergencia(
            tipo="titular_nao_encontrado",
            operadora="bradesco",
            referencia=familia.nome_titular,
            nome=familia.nome_titular,
            descricao="Titular não encontrado na API.",
            valor=familia.valor_total,
            num_vidas=familia.num_vidas,
            empresa=familia.empresa_planilha or "",
        )
    if len(candidatos) > 1:
        return None, Divergencia(
            tipo="nome_ambiguo",
            operadora="bradesco",
            referencia=familia.nome_titular,
            nome=familia.nome_titular,
            descricao=(
                f"Casa com {len(candidatos)} colaboradores homônimos — "
                "revisar manualmente."
            ),
            valor=familia.valor_total,
            num_vidas=familia.num_vidas,
            empresa=familia.empresa_planilha or "",
        )
    return candidatos[0], None


def _montar_item(familia: _Familia, colab: dict) -> ItemColaborador:
    return ItemColaborador(
        operadora=familia.operadora,
        competencia=familia.competencia,
        # Empresa de FATURAMENTO: NOME_EMPRESA da planilha (Unimed) — é a empresa
        # que a NF reflete. Só cai na empresa da API (rota) quando a planilha não
        # traz empresa (Bradesco). Garante rateado por empresa == NF por empresa.
        empresa=familia.empresa_planilha or str(colab.get("empresa", "")),
        cpf=normalizar_cpf(colab.get("cpf")) or "",
        nome=str(colab.get("nome", "")),
        centro_custo=str(colab.get("centro_custo", "")),
        classe_valor=str(colab.get("classe_valor", "")),
        matricula=str(colab.get("matricula", "")),
        num_vidas=familia.num_vidas,
        valor=familia.valor_total,
        situacao=str(colab.get("situacao", "")),
        pj=bool(colab.get("_pj", False)),
        vidas=[
            {
                "nome": linha.nome,
                "cpf": normalizar_cpf(linha.cpf) or "",
                "valor": linha.valor,
                "titular": linha.is_titular,
            }
            # Titular(es) primeiro, depois dependentes por nome.
            for linha in sorted(familia.linhas, key=lambda l: (not l.is_titular, l.nome))
        ],
    )


def _agregar(itens: list[ItemColaborador]) -> list[ItemAgregado]:
    acc: dict[tuple[str, str, str, str], list] = {}
    for item in itens:
        chave = (item.operadora, item.empresa, item.centro_custo, item.classe_valor)
        registro = acc.get(chave)
        if registro is None:
            acc[chave] = [Decimal("0"), 0]
            registro = acc[chave]
        registro[0] += item.valor
        registro[1] += 1
    return [
        ItemAgregado(
            operadora=op,
            empresa=emp,
            centro_custo=cc,
            classe_valor=classe,
            num_colaboradores=qtd,
            valor=valor,
        )
        for (op, emp, cc, classe), (valor, qtd) in acc.items()
    ]


def _total_faturado_por_empresa(planilhas: list[PlanilhaValores]) -> dict[str, Decimal]:
    """
    Soma de todo o VALOR TOTAL da planilha por empresa (NOME_EMPRESA normalizado).
    Inclui positivos, negativos e atípicas — é o total faturado que a NF/boleto
    reflete. Chave "" = sem empresa na planilha (ex.: Bradesco).
    """
    acc: dict[str, Decimal] = {}
    for planilha in planilhas:
        for linha in planilha.linhas:
            chave = _normalizar_nome(linha.empresa_planilha)
            acc[chave] = acc.get(chave, Decimal("0")) + linha.valor
        for atipica in planilha.atipicas:
            acc[""] = acc.get("", Decimal("0")) + atipica.valor
    return acc


def _totalizar(
    planilhas: list[PlanilhaValores],
    itens: list[ItemColaborador],
    estornos: list[Estorno],
    divergencias: list[Divergencia],
) -> list[TotaisOperadora]:
    operadoras = {p.operadora for p in planilhas}
    totais: list[TotaisOperadora] = []
    for op in sorted(operadoras):
        rateado = sum((i.valor for i in itens if i.operadora == op), Decimal("0"))
        est = sum((e.valor for e in estornos if e.operadora == op), Decimal("0"))
        nao_rateado = sum(
            (d.valor for d in divergencias if d.operadora == op), Decimal("0")
        )
        totais.append(
            TotaisOperadora(
                operadora=op,
                rateado=rateado,
                estornos=est,
                nao_rateado=nao_rateado,
                total=rateado + est + nao_rateado,
            )
        )
    return totais


def calcular(
    planilhas: list[PlanilhaValores],
    dados_externos: dict[str, Any],
) -> ResultadoRateio:
    """
    Executa o rateio e devolve o `ResultadoRateio`.

    Args:
        planilhas: saída de `parser.ler` (uma por operadora).
        dados_externos: deve conter `colaboradores` (lista da API), cada um com
            `cpf`, `nome`, `centro_custo`, `classe_valor`, `matricula` e
            `empresa` (marcada pelo router conforme a rota rest01/02/03).

    Returns:
        ResultadoRateio com itens, agregado, divergências e totais.
    """
    colaboradores = dados_externos.get(CHAVE_COLABORADORES) or []
    indices = _indexar_colaboradores(colaboradores)

    # Cadastro PJ (não vem da API): índices por CPF e por nome para o casamento
    # do titular não encontrado. `mapa` = {cpf: {nome, centro_custo, empresa, classe_valor}}.
    pj_mapa = (dados_externos.get("pj") or {}).get("mapa") or {}
    pj_por_cpf: dict[str, dict] = {}
    pj_por_nome: dict[str, dict] = {}
    for cpf_raw, dados in pj_mapa.items():
        cpf = normalizar_cpf(cpf_raw)
        if not cpf:
            continue
        entrada = {**dados, "cpf": cpf}
        pj_por_cpf[cpf] = entrada
        nome = _normalizar_nome(dados.get("nome"))
        if nome:
            pj_por_nome.setdefault(nome, entrada)

    resultado = ResultadoRateio()

    for familia in _agrupar_familias(planilhas):
        # Valor negativo (estorno): NÃO consulta a API — apenas subtrai no total.
        if familia.valor_total < 0:
            resultado.estornos.append(
                Estorno(
                    operadora=familia.operadora,
                    referencia=familia.nome_titular or familia.grupo_familiar,
                    valor=familia.valor_total,
                    num_vidas=familia.num_vidas,
                    empresa=(familia.titular.empresa_planilha if familia.titular else None) or "",
                )
            )
            continue

        colab, divergencia = _casar_familia(familia, indices, pj_por_cpf, pj_por_nome)
        if divergencia is not None:
            resultado.divergencias.append(divergencia)
            continue
        if colab is None:
            # Sem divergência, `_casar_familia` sempre devolve o colaborador; a
            # guarda existe para o caso nunca chegar como item sem colaborador.
            continue
        item = _montar_item(familia, colab)
        resultado.itens.append(item)
        # Demitido ainda cobrado: rateia normalmente, mas avisa (decisão do
        # negócio). Não entra em divergência para não afetar a reconciliação.
        if not _colaborador_ativo(colab):
            resultado.avisos.append(
                f"{item.operadora}: titular {item.nome} (situação "
                f"'{item.situacao}') rateado para {item.empresa} "
                f"(R$ {item.valor}) — verificar exclusão no plano."
            )

    # Linhas atípicas viram divergências (itens a tratar antes do ERP).
    for planilha in planilhas:
        for atipica in planilha.atipicas:
            resultado.divergencias.append(
                Divergencia(
                    tipo="atipico",
                    operadora=atipica.operadora,
                    referencia=atipica.descricao,
                    nome=atipica.descricao,
                    descricao=f"Lançamento atípico (fora do rateio): {atipica.descricao}",
                    valor=atipica.valor,
                )
            )

    resultado.agregado = _agregar(resultado.itens)
    resultado.totais = _totalizar(
        planilhas, resultado.itens, resultado.estornos, resultado.divergencias
    )
    resultado.total_faturado_por_empresa = _total_faturado_por_empresa(planilhas)
    resultado.totais_por_operadora_empresa = {
        (a.operadora, a.empresa): sum(
            (x.valor for x in resultado.agregado
             if x.operadora == a.operadora and x.empresa == a.empresa),
            Decimal("0"),
        )
        for a in resultado.agregado
    }
    return resultado
