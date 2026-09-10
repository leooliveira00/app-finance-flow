"""
Smoke test do rateio de PAGAMENTO da coparticipação (Unimed) com arquivos reais.

Rede de proteção do reuso da biblioteca compartilhada `_plano_saude`: garante que
o pipeline (parser_copart -> calculator -> validators) rateia por centro de custo
e que os totais por empresa RECONCILIAM com as NFs (Vertex/Zenith).

Auto-contido: os colaboradores da API são derivados do próprio consolidado (um
por titular, empresa pelo CNPJ), então não depende de rede/Protheus.

Como os arquivos de amostra NÃO são versionados como fonte de verdade
(`dados/`), o teste procura o diretório em COPART_DATA_DIR, depois em alguns
caminhos padrão, e PULA (sem falhar) se não encontrar.

Rodar (dentro do container, PYTHONPATH=/app):
    COPART_DATA_DIR=/tmp/copart python backend/tests/test_pagamento_coparticipacao.py
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal

from app.modules.pagamento_coparticipacao import parser_copart
from app.modules.pagamento_coparticipacao.module import (
    PagamentoCoparticipacaoUnimedRateio,
)

_CANDIDATOS = [
    os.environ.get("COPART_DATA_DIR", ""),
    "/tmp/copart",
    os.path.join(os.path.dirname(__file__), "..", "..", "dados", "pagamento_coparticipacao"),
]


def _achar_dados() -> str | None:
    for base in _CANDIDATOS:
        if base and os.path.isdir(base) and any(
            n.lower().endswith(".xlsx") for n in os.listdir(base)
        ):
            return base
    return None


def _carregar(base: str) -> dict[str, bytes]:
    arquivos: dict[str, bytes] = {}
    for nome in os.listdir(base):
        caminho = os.path.join(base, nome)
        if os.path.isfile(caminho):
            with open(caminho, "rb") as fh:
                arquivos[nome] = fh.read()
    return arquivos


def _mock_colaboradores(consolidado: bytes) -> list[dict]:
    """Um colaborador por titular; CC fictício por empresa (empresa vem do CNPJ)."""
    plan = parser_copart.ler_consolidado("consolidado", consolidado)
    vistos: dict[str, dict] = {}
    for linha in plan.linhas:
        cpf = linha.cpf_titular
        if cpf and cpf not in vistos:
            empresa = linha.empresa_planilha or "?"
            vistos[cpf] = {
                "cpf": cpf,
                "nome": linha.nome_titular or linha.nome,
                "centro_custo": "206010101" if empresa == "Vertex" else "206010102",
                "classe_valor": "3201002",
                "matricula": linha.matricula or "",
                "empresa": empresa,
                "situacao": "Situacao Normal",
            }
    return list(vistos.values())


def executar(base: str) -> None:
    arquivos = _carregar(base)
    consolidado = next(v for k, v in arquivos.items() if k.lower().endswith(".xlsx"))
    dados_externos = {"colaboradores": _mock_colaboradores(consolidado), "pj": {"mapa": {}}}

    modulo = PagamentoCoparticipacaoUnimedRateio()
    resultado = modulo.processar_completo(arquivos, dados_externos)

    # Toda família com titular na "API" deve ratear (0 divergências neste mock).
    assert not resultado.divergencias, (
        f"divergências inesperadas: {[d.tipo for d in resultado.divergencias]}"
    )

    # Soma por empresa dos itens rateados.
    por_empresa: dict[str, Decimal] = {}
    for item in resultado.itens:
        por_empresa[item.empresa] = por_empresa.get(item.empresa, Decimal("0")) + item.valor
    assert por_empresa, "nenhum item rateado"

    # Reconciliação: cada NF/boleto deve bater com o rateado da sua empresa.
    assert resultado.reconciliacao, "nenhuma NF/boleto reconciliada"
    for alerta in resultado.reconciliacao:
        assert alerta.bate, (
            f"reconciliação NÃO bate p/ {alerta.empresa}: "
            f"doc={alerta.valor_documento} base={alerta.valor_base}"
        )

    print(
        f"OK — {len(resultado.itens)} titulares, {len(resultado.agregado)} agregados; "
        f"reconciliação: "
        + ", ".join(f"{a.empresa}={a.valor_documento}" for a in resultado.reconciliacao)
    )


def test_pagamento_coparticipacao_reconcilia() -> None:
    base = _achar_dados()
    if base is None:
        import pytest  # type: ignore

        pytest.skip("dados de amostra ausentes (defina COPART_DATA_DIR)")
    executar(base)


if __name__ == "__main__":
    base = _achar_dados()
    if base is None:
        print("SKIP: dados de amostra não encontrados (defina COPART_DATA_DIR).")
        sys.exit(0)
    executar(base)
