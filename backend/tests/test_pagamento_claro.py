"""
Telefonia Claro: `calculator` (consolidação por centro de custo) e `titulos_erp`.

Cobre o que decide o valor e o destino de cada título no ERP: linhas agrupadas
por (centro de custo, classe de valor), o ajuste de conta rateado de forma que o
título feche EXATAMENTE com o boleto, o bloqueio por linha fora do cadastro e a
regra de um título por boleto.

Os boletos entram já como `BoletoClaro` (saída do parser): a leitura do PDF é
outra responsabilidade.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.modules.pagamento_claro import calculator
from app.modules.pagamento_claro.module import PagamentoClaroRateio
from app.modules.pagamento_claro.parser import (
    CATEGORIA_MENSALIDADE,
    CATEGORIA_USO,
    AjusteBoleto,
    BoletoClaro,
    LinhaBoleto,
    ServicoLinha,
)

CC_TI, CC_RH = "206010101", "206010102"
CLASSE = "3201002"


def _linha(numero: str, mensalidade: str, uso: str = "0") -> LinhaBoleto:
    return LinhaBoleto(
        numero=numero,
        numero_exibicao=f"({numero[:2]}) {numero[2:]}",
        servicos=[
            ServicoLinha("Plano", CATEGORIA_MENSALIDADE, Decimal(mensalidade)),
            ServicoLinha("Uso", CATEGORIA_USO, Decimal(uso)),
        ],
    )


def _boleto(linhas: list[LinhaBoleto], total: str, conta: str = "111",
            ajustes: list[AjusteBoleto] | None = None) -> BoletoClaro:
    return BoletoClaro(
        nome_arquivo=f"boleto_{conta}.pdf", conta=conta, competencia="07/2026",
        valor_total=Decimal(total), linhas=linhas, ajustes=ajustes or [],
    )


def _cad(centro_custo: str, classe_valor: str = CLASSE, **extra: Any) -> dict[str, Any]:
    return {"centro_custo": centro_custo, "classe_valor": classe_valor, "ativo": True, **extra}


CADASTRO = {
    "11900000001": _cad(CC_TI),
    "11900000002": _cad(CC_TI),
    "11900000003": _cad(CC_RH),
}


# ---------------------------------------------------------------------------
# Consolidação por centro de custo
# ---------------------------------------------------------------------------
def test_linhas_do_mesmo_destino_viram_um_item_do_titulo() -> None:
    boleto = _boleto(
        [_linha("11900000001", "40.00", "5.50"), _linha("11900000002", "40.00"),
         _linha("11900000003", "100.00")],
        total="185.50",
    )
    consolidado = calculator.consolidar_boleto(boleto, CADASTRO)

    itens = [(i["centro_custo"], i["qtd_linhas"], i["valor"])
             for i in consolidado["por_centro_custo"]]
    # Ordenado pelo valor: o maior item primeiro.
    assert itens == [(CC_RH, 1, Decimal("100.00")), (CC_TI, 2, Decimal("85.50"))]
    assert consolidado["confere"] and consolidado["qtd_incompletas"] == 0


def test_mesmo_centro_de_custo_com_classes_diferentes_nao_se_mistura() -> None:
    cadastro = {**CADASTRO, "11900000002": _cad(CC_TI, "3201099")}
    boleto = _boleto([_linha("11900000001", "40.00"), _linha("11900000002", "30.00")], "70.00")
    itens = calculator.consolidar_boleto(boleto, cadastro)["por_centro_custo"]
    assert {(i["centro_custo"], i["classe_valor"]) for i in itens} == {
        (CC_TI, CLASSE), (CC_TI, "3201099"),
    }


def test_destino_que_soma_zero_nao_vira_item() -> None:
    # O ERP recusa item de R$ 0,00; a linha segue visível no detalhamento.
    boleto = _boleto([_linha("11900000001", "40.00"), _linha("11900000003", "0.00")], "40.00")
    consolidado = calculator.consolidar_boleto(boleto, CADASTRO)
    assert [i["centro_custo"] for i in consolidado["por_centro_custo"]] == [CC_TI]
    assert consolidado["qtd_linhas"] == 2


# ---------------------------------------------------------------------------
# Ajuste de conta (ex.: crédito de faturas anteriores)
# ---------------------------------------------------------------------------
def test_ajuste_e_rateado_proporcionalmente_e_fecha_com_o_boleto() -> None:
    # Três destinos com o mesmo valor: -10,00 / 3 não é exato. O resíduo vai para
    # um item e a soma dos itens tem de ser EXATAMENTE o total do boleto.
    cadastro = {**CADASTRO, "11900000004": _cad("206010103")}
    boleto = _boleto(
        [_linha("11900000001", "50.00"), _linha("11900000003", "50.00"),
         _linha("11900000004", "50.00")],
        total="140.00",
        ajustes=[AjusteBoleto("Desconto Créditos Anteriores", Decimal("-10.00"))],
    )
    consolidado = calculator.consolidar_boleto(boleto, cadastro)
    itens = consolidado["por_centro_custo"]

    assert consolidado["confere"]
    assert sum(i["valor"] for i in itens) == Decimal("140.00")
    assert sum(i["ajuste"] for i in itens) == Decimal("-10.00")
    assert sorted(i["ajuste"] for i in itens) == [
        Decimal("-3.34"), Decimal("-3.33"), Decimal("-3.33"),
    ]
    assert all(i["valor_bruto"] == Decimal("50.00") for i in itens)


def test_ajuste_segue_a_proporcao_do_valor_de_cada_item() -> None:
    boleto = _boleto(
        [_linha("11900000001", "75.00"), _linha("11900000003", "25.00")],
        total="96.00",
        ajustes=[AjusteBoleto("Crédito", Decimal("-4.00"))],
    )
    por_cc = {i["centro_custo"]: i for i in
              calculator.consolidar_boleto(boleto, CADASTRO)["por_centro_custo"]}
    assert (por_cc[CC_TI]["ajuste"], por_cc[CC_RH]["ajuste"]) == (
        Decimal("-3.00"), Decimal("-1.00"),
    )


def test_boleto_com_cobranca_fora_do_detalhamento_nao_confere() -> None:
    boleto = _boleto([_linha("11900000001", "40.00")], total="45.00")
    consolidado = calculator.consolidar_boleto(boleto, CADASTRO)
    assert not consolidado["confere"]
    assert consolidado["diferenca"] == Decimal("5.00")


# ---------------------------------------------------------------------------
# Pendências de cadastro e bloqueio do envio
# ---------------------------------------------------------------------------
def test_linha_fora_do_cadastro_bloqueia_e_fica_fora_do_titulo() -> None:
    boleto = _boleto([_linha("11900000001", "40.00"), _linha("11999999999", "25.00")], "65.00")
    resultado = calculator.consolidar([boleto], CADASTRO)

    assert resultado["bloqueado"]
    assert resultado["bloqueios"] == ["1 linha(s) fora do cadastro, somando R$ 25.00."]
    (pendencia,) = resultado["pendencias"]
    assert (pendencia["numero"], pendencia["bloqueia"], pendencia["cadastrada"]) == (
        "11999999999", True, False,
    )
    itens = resultado["boletos"][0]["por_centro_custo"]
    assert [(i["centro_custo"], i["valor"]) for i in itens] == [(CC_TI, Decimal("40.00"))]


def test_linha_cadastrada_sem_classe_de_valor_tambem_bloqueia() -> None:
    cadastro = {**CADASTRO, "11900000002": _cad(CC_TI, classe_valor="")}
    boleto = _boleto([_linha("11900000002", "30.00")], "30.00")
    resultado = calculator.consolidar([boleto], cadastro)

    assert resultado["bloqueado"]
    (bloqueio,) = resultado["bloqueios"]
    assert "sem centro de custo ou sem classe" in bloqueio


def test_linha_fora_do_cadastro_cobrada_a_zero_nao_bloqueia() -> None:
    boleto = _boleto([_linha("11900000001", "40.00"), _linha("11999999999", "0.00")], "40.00")
    resultado = calculator.consolidar([boleto], CADASTRO)

    assert not resultado["bloqueado"]
    (pendencia,) = resultado["pendencias"]  # continua listada, para cadastrar já
    assert not pendencia["bloqueia"]
    assert resultado["totais"]["qtd_bloqueantes"] == 0


def test_mesma_linha_pendente_em_dois_boletos_vira_uma_pendencia() -> None:
    boletos = [
        _boleto([_linha("11999999999", "10.00")], "10.00", conta="111"),
        _boleto([_linha("11999999999", "15.00")], "15.00", conta="222"),
    ]
    (pendencia,) = calculator.consolidar(boletos, CADASTRO)["pendencias"]
    assert pendencia["valor"] == Decimal("25.00")
    assert pendencia["boletos"] == pendencia["contas"] == ["111", "222"]


def test_linha_que_mudou_de_conta_so_avisa() -> None:
    cadastro = {**CADASTRO, "11900000001": _cad(CC_TI, conta="999")}
    boleto = _boleto([_linha("11900000001", "40.00")], "40.00", conta="111")
    resultado = calculator.consolidar([boleto], cadastro)

    assert not resultado["bloqueado"]
    assert resultado["totais"]["qtd_conta_divergente"] == 1


# ---------------------------------------------------------------------------
# Visão agregada e títulos do ERP (um por boleto)
# ---------------------------------------------------------------------------
def _dois_boletos() -> dict[str, Any]:
    return calculator.consolidar(
        [
            _boleto([_linha("11900000001", "60.00"), _linha("11900000003", "40.00")],
                    "90.00", conta="111",
                    ajustes=[AjusteBoleto("Crédito", Decimal("-10.00"))]),
            _boleto([_linha("11900000002", "30.00")], "30.00", conta="222"),
        ],
        CADASTRO,
    )


def test_visao_agregada_usa_o_valor_ajustado_de_todos_os_boletos() -> None:
    agregado = {g["centro_custo"]: g for g in calculator.totais_por_centro_custo(_dois_boletos())}
    # TI: 60 - 6 (parte do crédito) no boleto 111 + 30 no 222.
    assert (agregado[CC_TI]["valor"], agregado[CC_TI]["qtd_linhas"]) == (Decimal("84.00"), 2)
    assert agregado[CC_RH]["valor"] == Decimal("36.00")
    assert sum(g["valor"] for g in agregado.values()) == Decimal("120.00")


def test_um_titulo_por_boleto_somando_o_valor_do_boleto() -> None:
    titulos = PagamentoClaroRateio().titulos_erp(_dois_boletos())

    assert [t["referencia"] for t in titulos] == ["111", "222"]
    for titulo in titulos:
        assert sum(l["valor"] for l in titulo["linhas"]) == titulo["valor"]
        assert f"conta {titulo['referencia']}" in titulo["observacao"]


def test_titulo_sem_conta_usa_o_arquivo_como_referencia() -> None:
    resultado = calculator.consolidar(
        [_boleto([_linha("11900000001", "40.00")], "40.00", conta="")], CADASTRO
    )
    (titulo,) = PagamentoClaroRateio().titulos_erp(resultado)
    assert titulo["referencia"] == "boleto_.pdf"
