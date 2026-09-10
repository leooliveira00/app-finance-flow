"""
Export TXT de redundância — importação manual no ERP quando o envio via API falha.

Layout POSICIONAL: uma linha por colaborador, campos concatenados lado a lado,
SEM separador nem espaço, nesta ordem:

    filial + matricula + cod_fornecedor + "569" + competencia + valor + cpf

Onde:
- `filial`, `matricula`, `cpf`: como vêm da API do Protheus (já zerados à
  esquerda — filial "01", matrícula "000589", CPF com 11 dígitos).
- `cod_fornecedor`: 2 dígitos por operadora — Unimed "07", Bradesco "03".
- `"569"`: valor padrão fixo do layout.
- `competencia`: pagamento no formato AAAAMM (6 dígitos, sem barra).
- `valor`: valor descontado com parte inteira zero-preenchida a 6 dígitos,
  ponto decimal e 2 casas (ex.: 125.31 -> "000125.31"; 1250.75 -> "001250.75").

Puro: recebe os `ItemRateio` já calculados (extras trazem filial/matrícula/
operadora) e devolve o texto. Não acessa banco nem rede.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.modules.base import ItemRateio

VALOR_PADRAO = "569"
LARGURA_INTEIRO = 6
# Fim de linha CRLF: o importador do ERP (Windows) só reconhece cada linha com
# \r\n. Toda linha é terminada (inclusive a última) para não "colar" registros.
TERMINADOR = "\r\n"
# Código do fornecedor no ERP por operadora (planilha de origem dos eventos).
COD_FORNECEDOR: dict[str, str] = {"unimed": "07", "bradesco": "03"}
# Colaborador com os DOIS planos entra numa única linha/lançamento, com os valores
# SOMADOS: a folha aceita um desconto por matrícula na competência. O código do
# fornecedor da linha consolidada é fixo (decisão do negócio) — a divisão por
# operadora continua visível na tela e no CSV, para auditoria.
COD_FORNECEDOR_CONSOLIDADO = "07"
_CENTAVOS = Decimal("0.01")


def _fmt_valor(valor: Decimal) -> str:
    """Parte inteira zero-preenchida a 6 dígitos + '.' + 2 casas decimais."""
    quantizado = valor.quantize(_CENTAVOS, ROUND_HALF_UP)
    inteiro, _, decimais = f"{quantizado:.2f}".partition(".")
    negativo = inteiro.startswith("-")
    inteiro = inteiro.lstrip("-").zfill(LARGURA_INTEIRO)
    return f"{'-' if negativo else ''}{inteiro}.{decimais}"


def _empresa_do_item(item: ItemRateio) -> str:
    return (item.extras.get("empresa", "") or "").strip().casefold()


def cod_fornecedor(operadoras: set[str]) -> str:
    """Código do fornecedor da linha: o da operadora, ou o consolidado se houver mais de uma."""
    if len(operadoras) == 1:
        return COD_FORNECEDOR.get(next(iter(operadoras)), "00")
    return COD_FORNECEDOR_CONSOLIDADO


def gerar(
    itens: list[ItemRateio],
    competencia: str,
    empresa: str | None = None,
) -> str:
    """Monta o TXT (uma linha por MATRÍCULA) para a competência informada.

    Colaborador com os dois planos entra numa linha só, com os valores SOMADOS e o
    código do fornecedor consolidado — mesma consolidação do envio via API (o TXT é
    a importação manual DO MESMO lançamento; divergir aqui importaria no ERP algo
    diferente do que a API manda).

    Ficam DE FORA os mesmos que o envio via API exclui:
    - PJ (`extras["pj"] == "sim"`): a API do Protheus não os retorna, não têm
      filial/matrícula e o desconto é cobrado na nota;
    - teto atingido (`extras["teto_aplicado"] == "sim"`) e demais bloqueios: exigem
      tratativa manual.

    Se `empresa` for informada, apenas os colaboradores dessa empresa entram —
    comparação case-insensitive (evita a pegadinha "Zenith"/"ZENITH").
    """
    alvo = empresa.strip().casefold() if empresa else None
    # Consolida por (filial, matrícula, CPF), preservando a ordem de aparição.
    consolidado: dict[tuple[str, str, str], dict] = {}
    for item in itens:
        if (
            item.extras.get("pj") == "sim"
            or item.extras.get("teto_aplicado") == "sim"
            or item.extras.get("bloqueado_envio") == "sim"
            or (alvo is not None and _empresa_do_item(item) != alvo)
        ):
            continue
        chave = (
            item.extras.get("filial", ""),
            item.extras.get("matricula", ""),
            item.colaborador_cpf,
        )
        registro = consolidado.setdefault(
            chave, {"valor": Decimal("0"), "operadoras": set()}
        )
        registro["valor"] += item.valor
        registro["operadoras"].add((item.extras.get("operadora", "") or "").lower())

    linhas = [
        f"{filial}{matricula}{cod_fornecedor(reg['operadoras'])}{VALOR_PADRAO}"
        f"{competencia}{_fmt_valor(reg['valor'])}{cpf}"
        for (filial, matricula, cpf), reg in consolidado.items()
    ]
    # Cada linha (inclusive a última) termina em CRLF -> o ERP reconhece o "Enter".
    return "".join(linha + TERMINADOR for linha in linhas)
