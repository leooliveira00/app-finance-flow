"""
Rateio do PAGAMENTO da coparticipação (Unimed): parser -> calculator -> reconciliação.

Rede de proteção do reuso da biblioteca compartilhada `_plano_saude`: garante que
o consolidado é rateado por centro de custo (família somada no titular) e que o
total por empresa RECONCILIA com a NF.

Os testes unitários montam o consolidado em memória (openpyxl), com dados
fictícios, e não dependem de arquivo, banco ou rede. A NF entra como
`DocumentoFatura` já extraído: a extração de PDF é outra responsabilidade
(`validators.extrair_documento`) e não é o que se testa aqui.

O smoke test com arquivos reais (consolidado + PDFs das NFs) é opcional: marker
`integration`, só roda com `--run-integration` e lê o diretório de
COPART_DATA_DIR.
"""

from __future__ import annotations

import os
from decimal import Decimal
from io import BytesIO
from typing import Any

import pytest
from openpyxl import Workbook

from app.modules._plano_saude import validators
from app.modules._plano_saude.calculator import ResultadoRateio
from app.modules._plano_saude.validators import DocumentoFatura
from app.modules.pagamento_coparticipacao import parser_copart
from app.modules.pagamento_coparticipacao.module import (
    PagamentoCoparticipacaoUnimedRateio,
)

# CNPJs do mapa padrão dos validators (fallback sem banco).
CNPJ_VERTEX = "23.456.780/0001-84"
CNPJ_ZENITH = "34.567.890/0001-30"

CABECALHO = [
    "REFERENCIA", "CNPJ", "NUM_CONTRATO", "MATRICULA_DO_BENEFICIARIO",
    "CPF_TITULAR", "NOME_TITULAR", "CPF_DEPENDENTE", "NOME_DEPENDENTE",
    "GRAU_DEPENDENCIA", "NOME_DEPENDENCIA", "VLR_PARTICIPACAO",
]

# Família Vertex: titular + dependente (somam no titular). Titular Zenith sozinho.
# Terceiro titular não está no cadastro da "API" -> divergência.
CPF_ANA, CPF_FILHO_ANA = "11111111111", "22222222222"
CPF_BRUNO = "33333333333"
CPF_DESCONHECIDO = "44444444444"


def _linha(cnpj: str, cpf_tit: str, nome_tit: str, cpf_dep: str, nome_dep: str,
           grau: int, valor: float) -> list[Any]:
    return [
        "202607", cnpj, "C-1", "M-" + cpf_dep[-3:], cpf_tit, nome_tit, cpf_dep, nome_dep,
        grau, "TITULAR" if grau == 0 else "FILHO", valor,
    ]


def _consolidado(linhas: list[list[Any]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(CABECALHO)
    for linha in linhas:
        ws.append(linha)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _colaborador(cpf: str, nome: str, empresa: str, centro_custo: str) -> dict[str, str]:
    return {
        "cpf": cpf,
        "nome": nome,
        "centro_custo": centro_custo,
        "classe_valor": "3201002",
        "matricula": "000" + cpf[-3:],
        "empresa": empresa,
        "situacao": "Situacao Normal",
    }


@pytest.fixture
def arquivos() -> dict[str, bytes]:
    return {
        "consolidado.xlsx": _consolidado([
            _linha(CNPJ_VERTEX, CPF_ANA, "ANA LIMA", CPF_ANA, "ANA LIMA", 0, 100.10),
            _linha(CNPJ_VERTEX, CPF_ANA, "ANA LIMA", CPF_FILHO_ANA, "LUCAS LIMA", 1, 50.25),
            _linha(CNPJ_ZENITH, CPF_BRUNO, "BRUNO SOUZA", CPF_BRUNO, "BRUNO SOUZA", 0, 80.00),
        ])
    }


@pytest.fixture
def dados_externos() -> dict[str, Any]:
    return {
        "colaboradores": [
            _colaborador(CPF_ANA, "ANA LIMA", "Vertex", "206010101"),
            _colaborador(CPF_BRUNO, "BRUNO SOUZA", "Zenith", "206010102"),
        ],
        "pj": {"mapa": {}},
    }


def _processar(arquivos: dict[str, bytes], dados_externos: dict[str, Any]) -> ResultadoRateio:
    return PagamentoCoparticipacaoUnimedRateio().processar_completo(arquivos, dados_externos)


def _nf(empresa: str, valor: str) -> DocumentoFatura:
    return DocumentoFatura(
        operadora="unimed", tipo="nf", nome_arquivo=f"nf_{empresa}.pdf",
        valor_total=Decimal(valor), empresa=empresa, numero="123",
    )


def test_valida_consolidado_e_recusa_planilha_sem_assinatura(arquivos: dict[str, bytes]) -> None:
    erros, _ = parser_copart.validar_estrutura(arquivos)
    assert erros == []

    # Planilha qualquer, sem CPF_TITULAR / VLR_PARTICIPACAO / CNPJ.
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["NOME", "VALOR"])
    buffer = BytesIO()
    wb.save(buffer)
    erros, _ = parser_copart.validar_estrutura({"x.xlsx": buffer.getvalue()})
    assert erros and "consolidado" in erros[0].lower()


def test_rateia_familia_no_titular_por_centro_de_custo(
    arquivos: dict[str, bytes], dados_externos: dict[str, Any]
) -> None:
    resultado = _processar(arquivos, dados_externos)

    assert resultado.divergencias == []
    por_cpf = {item.cpf: item for item in resultado.itens}
    assert set(por_cpf) == {CPF_ANA, CPF_BRUNO}

    ana = por_cpf[CPF_ANA]
    assert ana.valor == Decimal("150.35")  # titular + dependente, em Decimal exato
    assert ana.num_vidas == 2
    assert (ana.empresa, ana.centro_custo) == ("Vertex", "206010101")

    bruno = por_cpf[CPF_BRUNO]
    assert (bruno.empresa, bruno.valor) == ("Zenith", Decimal("80.00"))

    agregado = {(a.empresa, a.centro_custo): a.valor for a in resultado.agregado}
    assert agregado == {
        ("Vertex", "206010101"): Decimal("150.35"),
        ("Zenith", "206010102"): Decimal("80.00"),
    }


def test_reconciliacao_confere_nf_por_empresa(
    arquivos: dict[str, bytes], dados_externos: dict[str, Any]
) -> None:
    resultado = _processar(arquivos, dados_externos)
    alertas = validators.reconciliar(
        resultado, [_nf("Vertex", "150.35"), _nf("Zenith", "80.00")]
    )

    assert {a.empresa for a in alertas} == {"Vertex", "Zenith"}
    assert all(a.bate for a in alertas), [a.mensagem for a in alertas]


def test_reconciliacao_acusa_nf_divergente(
    arquivos: dict[str, bytes], dados_externos: dict[str, Any]
) -> None:
    resultado = _processar(arquivos, dados_externos)
    (alerta,) = validators.reconciliar(resultado, [_nf("Vertex", "160.35")])

    assert not alerta.bate
    assert alerta.diferenca == Decimal("10.00")


def test_titular_fora_do_cadastro_vira_divergencia_e_nao_entra_no_rateio(
    dados_externos: dict[str, Any],
) -> None:
    arquivos = {
        "consolidado.xlsx": _consolidado([
            _linha(CNPJ_VERTEX, CPF_ANA, "ANA LIMA", CPF_ANA, "ANA LIMA", 0, 100.00),
            _linha(CNPJ_VERTEX, CPF_DESCONHECIDO, "CARLA DIAS", CPF_DESCONHECIDO,
                   "CARLA DIAS", 0, 40.00),
        ])
    }
    resultado = _processar(arquivos, dados_externos)

    assert [i.cpf for i in resultado.itens] == [CPF_ANA]
    (divergencia,) = resultado.divergencias
    assert divergencia.tipo == "titular_nao_encontrado"
    assert divergencia.referencia == CPF_DESCONHECIDO
    assert divergencia.valor == Decimal("40.00")

    # A NF cobra os dois; o rateado não fecha e a diferença é o não encontrado.
    (alerta,) = validators.reconciliar(resultado, [_nf("Vertex", "140.00")])
    assert not alerta.bate
    assert alerta.diferenca == Decimal("40.00")


# ---------------------------------------------------------------------------
# Integração: arquivos reais de amostra (não versionados)
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_amostra_real_reconcilia() -> None:
    base = os.environ.get("COPART_DATA_DIR", "")
    if not os.path.isdir(base):
        pytest.fail("--run-integration exige COPART_DATA_DIR apontando para os dados de amostra")

    arquivos: dict[str, bytes] = {}
    for nome in os.listdir(base):
        caminho = os.path.join(base, nome)
        if os.path.isfile(caminho):
            with open(caminho, "rb") as fh:
                arquivos[nome] = fh.read()
    consolidado = next(v for k, v in arquivos.items() if k.lower().endswith(".xlsx"))

    # Um colaborador por titular do próprio consolidado: isola o teste do Protheus.
    colaboradores: dict[str, dict[str, str]] = {}
    for linha in parser_copart.ler_consolidado("consolidado", consolidado).linhas:
        if linha.cpf_titular and linha.cpf_titular not in colaboradores:
            empresa = linha.empresa_planilha or "?"
            colaboradores[linha.cpf_titular] = _colaborador(
                linha.cpf_titular, linha.nome_titular or linha.nome, empresa,
                "206010101" if empresa == "Vertex" else "206010102",
            )

    resultado = _processar(
        arquivos, {"colaboradores": list(colaboradores.values()), "pj": {"mapa": {}}}
    )
    assert not resultado.divergencias, [d.tipo for d in resultado.divergencias]
    assert resultado.reconciliacao, "nenhuma NF/boleto reconciliada"
    assert all(a.bate for a in resultado.reconciliacao), [
        a.mensagem for a in resultado.reconciliacao
    ]
