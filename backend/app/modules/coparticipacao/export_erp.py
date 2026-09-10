"""
Payload do POST de coparticipação no ERP (rotina GPE — desconto em folha).

Formato: LISTA de entradas, uma por MATRÍCULA, cada uma com HEADER (a matrícula) e
ITENS (um por operadora do colaborador na competência):

    [{"HEADER": {"FILIAL": "01", "RA_MAT": "000606"},
      "ITENS": [{"RHO_FILIAL": "01", "RHO_DTOCOR": "20260806", "RHO_TPFORN": "1",
                 "RHO_CODFOR": "07", "RHO_ORIGEM": "1", "RHO_PD": "569",
                 "RHO_COMPPG": "202608", "RHO_TPLAN": "1",
                 "RHO_CPF": "05371671102", "RHO_VLRFUN": 100}]}]

Campos:
- `FILIAL`/`RHO_FILIAL`, `RA_MAT`, `RHO_CPF`: como vêm da API do Protheus.
- `RHO_CODFOR`: operadora — Unimed "07", Bradesco "03" (mesmo mapa do TXT). Quem
  tem os DOIS planos entra numa entrada só, com os valores somados e o código
  consolidado (`COD_FORNECEDOR_CONSOLIDADO`) — a folha aceita um desconto por
  matrícula na competência.
- `RHO_DTOCOR`: data de inserção do registro (AAAAMMDD) — recebida de fora para
  o módulo seguir puro/testável.
- `RHO_COMPPG`: competência de PAGAMENTO (AAAAMM), informada no envio.
- `RHO_VLRFUN`: valor a descontar, NUMÉRICO (não string, conforme a spec).
- `RHO_TPFORN`, `RHO_ORIGEM`, `RHO_PD`, `RHO_TPLAN`: fixos do layout.

Puro: recebe os itens do snapshot da execução (dicts) e devolve o payload. Não
acessa banco nem rede. Espelha o [export_txt.py] — mesmo conteúdo, outro
transporte —, por isso reaproveita `cod_fornecedor()` e `VALOR_PADRAO` dele.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from .export_txt import VALOR_PADRAO, cod_fornecedor

# Fixos do layout (mesmos para todo registro).
TIPO_FORNECEDOR = "1"
ORIGEM = "1"
TIPO_PLANO = "1"
_CENTAVOS = Decimal("0.01")


def _texto(valor: Any) -> str:
    return str(valor or "").strip()


def _valor(bruto: Any) -> Decimal:
    """Valor como Decimal com 2 casas (o snapshot serializa Decimal como string)."""
    try:
        return Decimal(_texto(bruto) or "0").quantize(_CENTAVOS, ROUND_HALF_UP)
    except InvalidOperation:
        return Decimal("0")


def _empresa(item: dict[str, Any]) -> str:
    return _texto(item.get("empresa")).casefold()


def elegivel(item: dict[str, Any]) -> bool:
    """
    Quem entra no lançamento em folha.

    Fora:
    - `bloqueado_envio`: exige tratativa manual (PJ ou teto atingido).
    - PJ e `teto_aplicado` também são checados diretamente: snapshots gravados
      antes de `bloqueado_envio` existir não têm a marca, e um deles reenviado
      não pode passar a mandar quem a regra exclui.
    - sem matrícula/filial: não há folha onde descontar.
    - valor zerado: registro de desconto zero só polui a folha.
    """
    if item.get("bloqueado_envio") in (True, "sim"):
        return False
    if item.get("pj") in (True, "sim") or item.get("teto_aplicado") in (True, "sim"):
        return False
    if not _texto(item.get("matricula")) or not _texto(item.get("filial")):
        return False
    return _valor(item.get("valor_descontado")) > 0


def _item_erp(
    filial: str,
    cpf: str,
    valor: Decimal,
    operadoras: set[str],
    competencia: str,
    data_ocorrencia: str,
) -> dict[str, Any]:
    return {
        "RHO_FILIAL": filial,
        "RHO_DTOCOR": data_ocorrencia,
        "RHO_TPFORN": TIPO_FORNECEDOR,
        "RHO_CODFOR": cod_fornecedor(operadoras),
        "RHO_ORIGEM": ORIGEM,
        "RHO_PD": VALOR_PADRAO,
        "RHO_COMPPG": competencia,
        "RHO_TPLAN": TIPO_PLANO,
        "RHO_CPF": cpf,
        "RHO_VLRFUN": float(valor),
    }


def gerar(
    itens: list[dict[str, Any]],
    competencia: str,
    data_ocorrencia: str,
    empresa: str | None = None,
    matriculas: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Monta o payload do lote para a competência de pagamento informada.

    Args:
        itens: itens do snapshot da execução (cpf, nome, matricula, filial,
            operadora, empresa, valor_descontado, pj).
        competencia: competência de PAGAMENTO em AAAAMM.
        data_ocorrencia: data de inserção do registro em AAAAMMDD.
        empresa: se informada, só os colaboradores dela entram (comparação
            case-insensitive — evita a pegadinha "Zenith"/"ZENITH").
        matriculas: se informado, só estas matrículas entram — é o REENVIO
            SELETIVO das que o ERP recusou, para não reenviar (e arriscar
            duplicar) as que ele já aceitou.

    Um colaborador com os DOIS planos entra numa ÚNICA entrada, com os valores
    SOMADOS: a folha aceita um desconto por matrícula na competência. O
    `RHO_CODFOR` da entrada consolidada é o `COD_FORNECEDOR_CONSOLIDADO` (07) —
    quem tem um único plano mantém o código dele (03 ou 07). A divisão por
    operadora não se perde: continua no resultado, na tela e no CSV.
    """
    alvo = empresa.strip().casefold() if empresa else None
    # Consolida por matrícula (a folha é por matrícula), somando os planos.
    acumulado: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in itens:
        if not elegivel(item) or (alvo is not None and _empresa(item) != alvo):
            continue
        if matriculas is not None and _texto(item.get("matricula")) not in matriculas:
            continue
        chave = (
            _texto(item.get("filial")),
            _texto(item.get("matricula")),
            _texto(item.get("cpf")),
        )
        registro = acumulado.setdefault(chave, {"valor": Decimal("0"), "operadoras": set()})
        registro["valor"] += _valor(item.get("valor_descontado"))
        registro["operadoras"].add(_texto(item.get("operadora")).lower())

    return [
        {
            "HEADER": {"FILIAL": filial, "RA_MAT": matricula},
            "ITENS": [
                _item_erp(
                    filial, cpf, reg["valor"], reg["operadoras"], competencia, data_ocorrencia
                )
            ],
        }
        for (filial, matricula, cpf), reg in acumulado.items()
    ]
