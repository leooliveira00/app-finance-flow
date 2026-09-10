"""
Cálculo da coparticipação (regra de negócio pura).

Para cada colaborador (titular + dependentes, agrupados por `CPF Titular`):
1. Descobre a FAIXA pelo salário do colaborador (API).
2. Para cada evento, o valor a descontar é FIXO por (faixa, tipo de exame),
   vindo da tabela de consenso.
3. Soma os eventos -> valor bruto. Um ITEM POR OPERADORA (dois planos = dois
   itens, porque no ERP o código da operadora identifica o plano).
4. Aplica o TETO, que é da PESSOA (`teto_percentual`% do salário sobre a soma dos
   planos): quem o atinge fica `bloqueado_envio` — não vai ao ERP e exige
   tratativa manual —, com aviso e o valor rateado entre os planos.

Entradas via `dados_externos`:
- `colaboradores`: lista da API, cada um com `cpf`, `nome`, `salario`, `matricula`,
  `filial` (e opcionalmente `empresa`, `centro_custo`).
- `consenso`: {`teto_percentual`, `faixas`: [{`nome`, `salario_inicial`,
  `salario_final`, `valores`: {`consulta`, `simples`, `especial`}}]}.

Puro: não acessa banco nem rede.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .parser import Consolidado, EventoCoparticipacao, normalizar_cpf

CHAVE_COLABORADORES = "colaboradores"
CHAVE_CONSENSO = "consenso"
CHAVE_PJ = "pj"
# Marca posta pelo cliente do Protheus (`services.protheus.CHAVE_AMBIGUIDADE`) no
# colaborador cujo CPF tem registros não-demitidos EQUIVALENTES em empresas ou
# matrículas diferentes — escolha indecidível. Chave lida como literal, igual às
# demais do colaborador ("salario", "matricula"), para o módulo seguir puro.
CHAVE_AMBIGUIDADE = "_ambiguidade"
_CENTAVOS = Decimal("0.01")
TIPOS = ("consulta", "simples", "especial")


# ---------------------------------------------------------------------------
# Estruturas de saída
# ---------------------------------------------------------------------------
@dataclass
class ItemCoparticipacao:
    """Desconto de coparticipação de um colaborador."""

    cpf: str
    nome: str
    matricula: str
    filial: str                 # filial do colaborador na API (ex.: "01") — p/ ERP
    operadora: str              # "unimed" | "bradesco" (origem dos eventos) — p/ ERP
    empresa: str
    salario: Decimal
    faixa: str
    num_eventos: int
    valor_bruto: Decimal        # soma dos valores da tabela (antes do teto)
    teto: Decimal               # teto_percentual% do salário
    valor_descontado: Decimal   # min(valor_bruto, teto)
    teto_aplicado: bool
    por_tipo: dict[str, str] = field(default_factory=dict)  # breakdown (Decimal->str)
    ocorrencias: list[dict] = field(default_factory=list)   # eventos do colaborador
    pj: bool = False                                        # colaborador PJ (salário padrão)
    # Fora do lançamento automático em folha — exige tratativa manual. Dois casos:
    # PJ (não tem matrícula/filial; cobrado na nota) e teto atingido (decisão do
    # negócio: quem estoura o percentual não vai ao ERP). O motivo é exibido na UI.
    bloqueado_envio: bool = False
    motivo_bloqueio: str = ""


@dataclass
class DivergenciaCopart:
    # titular_nao_encontrado | colaborador_desligado | sem_salario | sem_faixa |
    # procedimento_nao_classificado
    tipo: str
    cpf: str
    nome: str
    descricao: str
    num_eventos: int = 0


@dataclass
class ResultadoCoparticipacao:
    itens: list[ItemCoparticipacao] = field(default_factory=list)
    divergencias: list[DivergenciaCopart] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    total_descontado: Decimal = Decimal("0")


# ---------------------------------------------------------------------------
# Consenso (faixas + valores + teto)
# ---------------------------------------------------------------------------
def _dec(valor: Any) -> Decimal:
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


# Situações consideradas inativas (colaborador desligado).
SITUACOES_INATIVAS = {"DEMITIDO"}


def _ativo(colab: dict) -> bool:
    return str(colab.get("situacao", "")).strip().upper() not in SITUACOES_INATIVAS


def _faixa_do_salario(salario: Decimal, faixas: list[dict]) -> dict | None:
    for faixa in faixas:
        ini = _dec(faixa.get("salario_inicial", 0))
        fim = _dec(faixa.get("salario_final", 0))
        if ini <= salario <= fim:
            return faixa
    return None


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------
def _agrupar_por_titular(
    consolidados: list[Consolidado],
) -> dict[str, list[EventoCoparticipacao]]:
    grupos: dict[str, list[EventoCoparticipacao]] = {}
    for consolidado in consolidados:
        for evento in consolidado.eventos:
            grupos.setdefault(evento.cpf_titular, []).append(evento)
    return grupos


def _agrupar_por_operadora(
    eventos: list[EventoCoparticipacao],
) -> dict[str, list[EventoCoparticipacao]]:
    """
    Separa os eventos do titular POR OPERADORA, preservando a ordem de aparição.

    Um titular normalmente está numa única operadora, mas quem tem os dois planos
    gera um item (e um lançamento) por operadora: no ERP é o `RHO_CODFOR` — 03
    Bradesco / 07 Unimed — que identifica de qual plano é o desconto, então somar
    os dois num registro só mandaria dinheiro do Bradesco com código da Unimed.
    """
    grupos: dict[str, list[EventoCoparticipacao]] = {}
    for evento in eventos:
        grupos.setdefault(evento.operadora or "", []).append(evento)
    return grupos


def _precificar(
    resultado: ResultadoCoparticipacao,
    cpf: str,
    nome: str,
    eventos: list[EventoCoparticipacao],
    valores_faixa: dict,
) -> tuple[dict[str, Decimal], int, list[dict]]:
    """Aplica a tabela da faixa aos eventos -> (por_tipo, num_eventos, ocorrências).

    Evento com procedimento não classificado vira divergência e não é precificado.
    """
    por_tipo = {t: Decimal("0") for t in TIPOS}
    num_eventos = 0
    ocorrencias: list[dict] = []
    for evento in eventos:
        tipo_evento = evento.tipo or ""
        classificado = tipo_evento in valores_faixa
        valor_aplicado = _dec(valores_faixa[tipo_evento]) if classificado else Decimal("0")
        if classificado:
            por_tipo[tipo_evento] += valor_aplicado
            num_eventos += 1
        else:
            resultado.divergencias.append(
                DivergenciaCopart(
                    tipo="procedimento_nao_classificado", cpf=cpf, nome=nome,
                    descricao=f"Procedimento '{evento.procedimento}' não classificado em consulta/simples/especial.",
                    num_eventos=1,
                )
            )
        ocorrencias.append(
            {
                "beneficiario": evento.nome_beneficiario,
                "data": evento.data_atendimento.isoformat() if evento.data_atendimento else "",
                "procedimento": evento.procedimento,
                "tipo": evento.tipo or "",
                "valor": valor_aplicado,
                "classificado": classificado,
            }
        )
    return por_tipo, num_eventos, ocorrencias


def _processar_colaborador(
    resultado: ResultadoCoparticipacao,
    cpf: str,
    eventos: list[EventoCoparticipacao],
    nome: str,
    matricula: str,
    filial: str,
    empresa: str,
    salario: Decimal,
    faixas: list[dict],
    teto_pct: Decimal,
    pj: bool,
    registros_equivalentes: list[str] | None = None,
) -> None:
    """
    Precifica os eventos de um colaborador (API ou PJ) e monta os itens.

    UM ITEM POR OPERADORA (quem tem os dois planos gera dois) — cada lançamento no
    ERP carrega o código da sua operadora.

    O TETO É DA PESSOA, não do plano: `teto_pct`% do salário sobre a SOMA dos
    planos (senão quem tem dois planos poderia ser descontado no dobro). Quem
    atinge o teto NÃO vai ao ERP: fica marcado `bloqueado_envio` para tratativa
    manual — decisão do negócio, e é o que os exports e o envio respeitam.

    `registros_equivalentes` (quando presente) são os registros não-demitidos
    empatados do mesmo CPF em empresas/matrículas diferentes — transferência no
    grupo sem baixa no cadastro de origem. `empresa`/`matricula`/`filial` já vêm do
    registro que deu o salário, mas com empate não há como saber qual é o correto:
    também fica fora do lançamento automático, porque descontar na folha da empresa
    errada é pior do que não descontar.
    """
    faixa = _faixa_do_salario(salario, faixas)
    if faixa is None:
        resultado.divergencias.append(
            DivergenciaCopart(
                tipo="sem_faixa", cpf=cpf, nome=nome,
                descricao=f"Salário R$ {salario} não se enquadra em nenhuma faixa cadastrada.",
                num_eventos=len(eventos),
            )
        )
        return

    valores_faixa = faixa.get("valores") or {}
    por_operadora = _agrupar_por_operadora(eventos)
    # Precifica cada operadora separadamente; o teto é decidido depois, na soma.
    parciais = [
        (operadora, *_precificar(resultado, cpf, nome, eventos_op, valores_faixa))
        for operadora, eventos_op in por_operadora.items()
    ]

    bruto_pessoa = sum((sum(p[1].values(), Decimal("0")) for p in parciais), Decimal("0"))
    teto = (salario * teto_pct / Decimal("100")).quantize(_CENTAVOS, ROUND_HALF_UP)
    teto_aplicado = bruto_pessoa > teto

    for operadora, por_tipo, num_eventos, ocorrencias in parciais:
        valor_bruto = sum(por_tipo.values(), Decimal("0"))
        if teto_aplicado:
            # Não vai ao ERP; o valor exibido é a parte deste plano no teto da
            # pessoa (proporcional ao bruto), para a tratativa manual ter a conta.
            valor_descontado = (
                (teto * valor_bruto / bruto_pessoa).quantize(_CENTAVOS, ROUND_HALF_UP)
                if bruto_pessoa > 0
                else Decimal("0")
            )
        else:
            valor_descontado = valor_bruto
        ambiguo = bool(registros_equivalentes)
        bloqueado = pj or teto_aplicado or ambiguo
        resultado.itens.append(
            ItemCoparticipacao(
                cpf=cpf,
                nome=nome,
                matricula=matricula,
                filial=filial,
                operadora=operadora,
                empresa=empresa,
                salario=salario,
                faixa=str(faixa.get("nome", "")),
                num_eventos=num_eventos,
                valor_bruto=valor_bruto,
                teto=teto,
                valor_descontado=valor_descontado,
                teto_aplicado=teto_aplicado,
                por_tipo={t: str(v) for t, v in por_tipo.items()},
                ocorrencias=ocorrencias,
                pj=pj,
                bloqueado_envio=bloqueado,
                motivo_bloqueio=(
                    f"Teto de {teto_pct}% atingido: requer tratativa manual; não enviado ao ERP."
                    if teto_aplicado
                    else "Colaborador PJ: desconto cobrado na nota fiscal, em tratativa manual."
                    if pj
                    else (
                        "Registro ativo equivalente em mais de uma empresa "
                        f"({', '.join(registros_equivalentes or [])}): não é possível definir a "
                        "folha do desconto; requer tratativa manual."
                    )
                    if ambiguo
                    else ""
                ),
            )
        )

    if teto_aplicado:
        resultado.avisos.append(
            f"{nome}: desconto bruto de R$ {bruto_pessoa} atinge o teto de {teto_pct}% "
            f"(R$ {teto}). Não será enviado ao ERP; requer tratativa manual."
        )
    if registros_equivalentes:
        resultado.avisos.append(
            f"{nome}: registro ativo equivalente em mais de uma empresa "
            f"({', '.join(registros_equivalentes)}) — considerado {empresa}/{matricula} "
            f"(origem do salário). Confirme a transferência no Protheus; não será "
            f"enviado ao ERP."
        )


def calcular(
    consolidados: list[Consolidado],
    dados_externos: dict[str, Any],
) -> ResultadoCoparticipacao:
    colaboradores = dados_externos.get(CHAVE_COLABORADORES) or []
    consenso = dados_externos.get(CHAVE_CONSENSO) or {}
    faixas = consenso.get("faixas") or []
    teto_pct = _dec(consenso.get("teto_percentual", 20))

    pj_cfg = dados_externos.get(CHAVE_PJ) or {}
    pj_cpfs = {normalizar_cpf(c) for c in (pj_cfg.get("cpfs") or []) if normalizar_cpf(c)}
    salario_pj = _dec(pj_cfg.get("salario_padrao", 10000))

    por_cpf = {
        normalizar_cpf(c.get("cpf")): c for c in colaboradores if normalizar_cpf(c.get("cpf"))
    }

    resultado = ResultadoCoparticipacao()

    for cpf_titular, eventos in _agrupar_por_titular(consolidados).items():
        nome_consolidado = eventos[0].nome_titular if eventos else ""

        # PJ: salário fixo, NÃO consulta a API.
        if cpf_titular in pj_cpfs:
            _processar_colaborador(
                resultado, cpf_titular, eventos, nome_consolidado, "", "", "PJ",
                salario_pj, faixas, teto_pct, pj=True,
            )
            continue

        colab = por_cpf.get(cpf_titular)
        if colab is None:
            resultado.divergencias.append(
                DivergenciaCopart(
                    tipo="titular_nao_encontrado", cpf=cpf_titular, nome=nome_consolidado,
                    descricao="Titular não encontrado na API (sem salário para a faixa).",
                    num_eventos=len(eventos),
                )
            )
            continue

        # Somente colaboradores ATIVOS entram no rateio; desligados -> divergência.
        if not _ativo(colab):
            resultado.divergencias.append(
                DivergenciaCopart(
                    tipo="colaborador_desligado", cpf=cpf_titular,
                    nome=str(colab.get("nome", nome_consolidado)),
                    descricao=f"Colaborador desligado (situação '{colab.get('situacao', '')}') — não considerado no rateio.",
                    num_eventos=len(eventos),
                )
            )
            continue

        # Registro com salário ZERADO é desconsiderado: é cadastro funcional/casca
        # (ex.: "Rh Vertex"), não vínculo com folha. Sem salário não há faixa, e
        # deixar passar geraria um item de R$ 0,00 mascarado como desconto válido.
        # O dedup já prefere o registro COM salário quando o CPF tem os dois.
        salario = _dec(colab.get("salario", 0))
        if salario <= 0:
            resultado.divergencias.append(
                DivergenciaCopart(
                    tipo="sem_salario", cpf=cpf_titular,
                    nome=str(colab.get("nome", nome_consolidado)),
                    descricao=(
                        f"Registro sem salário na API ({colab.get('empresa', '')}/"
                        f"{colab.get('matricula', '')}) — desconsiderado: não há base para a faixa."
                    ),
                    num_eventos=len(eventos),
                )
            )
            continue

        # empresa/matrícula/filial vêm do MESMO registro que deu o salário (o
        # não-demitido escolhido em `protheus.resolver_duplicados`) — é o que
        # garante que o desconto entre na folha onde a pessoa está hoje.
        _processar_colaborador(
            resultado, cpf_titular, eventos, str(colab.get("nome", nome_consolidado)),
            str(colab.get("matricula", "")), str(colab.get("filial", "")),
            str(colab.get("empresa", "")),
            salario, faixas, teto_pct, pj=False,
            registros_equivalentes=colab.get(CHAVE_AMBIGUIDADE),
        )

    resultado.total_descontado = sum(
        (i.valor_descontado for i in resultado.itens), Decimal("0")
    )
    return resultado
