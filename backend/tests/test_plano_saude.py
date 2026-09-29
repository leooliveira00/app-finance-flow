"""
Mensalidade do plano de saúde: `_plano_saude.calculator` (+ reconciliação).

Biblioteca compartilhada por `pagamento_unimed`, `pagamento_bradesco` e
`pagamento_coparticipacao`. Cobre o casamento planilha × API (Unimed por CPF,
Bradesco por nome), a família somada no titular, estornos, demitidos, PJ,
atípicas e o fechamento dos totais com a NF/boleto.

As linhas entram já como `LinhaValor` (saída do parser): o layout das planilhas
das operadoras é outra responsabilidade.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.modules._plano_saude import calculator, validators
from app.modules._plano_saude.calculator import ResultadoRateio
from app.modules._plano_saude.parser import LinhaAtipica, LinhaValor, PlanilhaValores
from app.modules._plano_saude.validators import DocumentoFatura

CPF_ANA, CPF_FILHA = "11111111111", "22222222222"
CPF_BRUNO = "33333333333"


def _unimed(cpf_tit: str, cpf: str, nome: str, valor: str, titular: bool = True,
            empresa: str = "Vertex") -> LinhaValor:
    return LinhaValor(
        operadora="unimed", competencia="202607", grupo_familiar=cpf_tit,
        is_titular=titular, nome=nome, valor=Decimal(valor), cpf=cpf,
        cpf_titular=cpf_tit, empresa_planilha=empresa,
    )


def _bradesco(certificado: str, nome: str, valor: str, titular: bool = True,
              nome_titular: str | None = None) -> LinhaValor:
    return LinhaValor(
        operadora="bradesco", competencia="202607", grupo_familiar=certificado,
        is_titular=titular, nome=nome, valor=Decimal(valor),
        nome_titular=nome_titular,
    )


def _planilha(operadora: str, linhas: list[LinhaValor],
              atipicas: list[LinhaAtipica] | None = None) -> PlanilhaValores:
    return PlanilhaValores(
        operadora=operadora, competencia="202607", nome_arquivo=f"{operadora}.xlsx",
        linhas=linhas, atipicas=atipicas or [],
    )


def _colab(cpf: str, nome: str, centro_custo: str = "206010101",
           empresa: str = "Vertex", **extra: Any) -> dict[str, Any]:
    return {
        "cpf": cpf, "nome": nome, "centro_custo": centro_custo, "classe_valor": "3201002",
        "matricula": "000" + cpf[-3:], "empresa": empresa, "situacao": "Situacao Normal",
        **extra,
    }


def _calcular(planilhas: list[PlanilhaValores], colaboradores: list[dict[str, Any]],
              pj: dict[str, Any] | None = None) -> ResultadoRateio:
    return calculator.calcular(
        planilhas, {"colaboradores": colaboradores, "pj": {"mapa": pj or {}}}
    )


# ---------------------------------------------------------------------------
# Casamento planilha × API
# ---------------------------------------------------------------------------
def test_unimed_casa_por_cpf_e_soma_a_familia_no_titular() -> None:
    resultado = _calcular(
        [_planilha("unimed", [
            _unimed(CPF_ANA, CPF_FILHA, "LIA LIMA", "150.00", titular=False),
            _unimed(CPF_ANA, CPF_ANA, "ANA LIMA", "300.50"),
        ])],
        # Nome diferente na API: a Unimed casa só pelo CPF do titular.
        [_colab(CPF_ANA, "ANA MARIA LIMA", empresa="Zenith")],
    )
    (item,) = resultado.itens
    assert (item.valor, item.num_vidas, item.centro_custo) == (
        Decimal("450.50"), 2, "206010101",
    )
    # Empresa de FATURAMENTO vem da planilha (é a que a NF reflete), não da API.
    assert item.empresa == "Vertex"
    assert [v["titular"] for v in item.vidas] == [True, False]  # titular primeiro


def test_bradesco_casa_por_nome_normalizado_e_usa_empresa_da_api() -> None:
    resultado = _calcular(
        [_planilha("bradesco", [
            _bradesco("C1", "JOSÉ  da silva", "200.00"),
            _bradesco("C1", "PEDRO DA SILVA", "80.00", titular=False),
        ])],
        [_colab(CPF_BRUNO, "Jose da Silva", centro_custo="206010102", empresa="Zenith")],
    )
    (item,) = resultado.itens
    assert (item.cpf, item.valor, item.empresa) == (CPF_BRUNO, Decimal("280.00"), "Zenith")


def test_bradesco_com_homonimos_vira_divergencia() -> None:
    resultado = _calcular(
        [_planilha("bradesco", [_bradesco("C1", "JOSE DA SILVA", "200.00")])],
        [_colab(CPF_ANA, "JOSE DA SILVA"), _colab(CPF_BRUNO, "José da Silva")],
    )
    assert resultado.itens == []
    (divergencia,) = resultado.divergencias
    assert divergencia.tipo == "nome_ambiguo"
    assert "2 colaboradores" in divergencia.descricao


def test_bradesco_sem_linha_nem_nome_de_titular_vira_divergencia() -> None:
    resultado = _calcular(
        [_planilha("bradesco", [_bradesco("C9", "DEPENDENTE", "50.00", titular=False)])],
        [],
    )
    assert [d.tipo for d in resultado.divergencias] == ["sem_titular"]


# ---------------------------------------------------------------------------
# Estornos, demitidos, PJ e atípicas
# ---------------------------------------------------------------------------
def test_estorno_nao_consulta_a_api_e_so_abate_do_total() -> None:
    # Titular fora da API (já saiu da empresa), mas com valor NEGATIVO: é crédito.
    resultado = _calcular(
        [_planilha("unimed", [_unimed(CPF_BRUNO, CPF_BRUNO, "BRUNO", "-120.00")])], []
    )
    assert resultado.itens == [] and resultado.divergencias == []
    (estorno,) = resultado.estornos
    assert (estorno.valor, estorno.empresa) == (Decimal("-120.00"), "Vertex")


def test_demitido_ainda_cobrado_e_rateado_com_aviso() -> None:
    resultado = _calcular(
        [_planilha("unimed", [_unimed(CPF_ANA, CPF_ANA, "ANA", "300.00")])],
        [_colab(CPF_ANA, "ANA", situacao="Demitido")],
    )
    (item,) = resultado.itens
    assert item.valor == Decimal("300.00")
    assert resultado.divergencias == []  # não pode afetar a reconciliação
    assert any("Demitido" in aviso for aviso in resultado.avisos)


def test_pj_com_centro_de_custo_e_rateado_e_sem_vira_divergencia() -> None:
    cpf_pj_sem_cc = "44444444444"
    resultado = _calcular(
        [_planilha("unimed", [
            _unimed(CPF_BRUNO, CPF_BRUNO, "BRUNO PJ", "90.00"),
            _unimed(cpf_pj_sem_cc, cpf_pj_sem_cc, "CARLA PJ", "70.00"),
        ])],
        [],
        pj={
            CPF_BRUNO: {"nome": "BRUNO PJ", "centro_custo": "206010105", "empresa": "Vertex"},
            cpf_pj_sem_cc: {"nome": "CARLA PJ", "centro_custo": ""},
        },
    )
    (item,) = resultado.itens
    assert (item.cpf, item.pj, item.centro_custo) == (CPF_BRUNO, True, "206010105")
    (divergencia,) = resultado.divergencias
    assert (divergencia.tipo, divergencia.referencia) == ("colaborador_pj", cpf_pj_sem_cc)


def test_atipica_fica_fora_do_rateio_mas_entra_no_faturado() -> None:
    resultado = _calcular(
        [_planilha(
            "bradesco", [_bradesco("C1", "ANA", "100.00")],
            atipicas=[LinhaAtipica(operadora="bradesco", descricao="TAXA", valor=Decimal("7.50"))],
        )],
        [_colab(CPF_ANA, "ANA")],
    )
    assert [d.tipo for d in resultado.divergencias] == ["atipico"]
    # Sem empresa na planilha (Bradesco), o faturado fica na chave "".
    assert resultado.total_faturado_por_empresa == {"": Decimal("107.50")}


# ---------------------------------------------------------------------------
# Totais, agregado e reconciliação
# ---------------------------------------------------------------------------
def _cenario_misto() -> ResultadoRateio:
    """Vertex: Ana (CC 1) + Bruno (CC 1) + estorno; e um titular não encontrado."""
    return _calcular(
        [_planilha("unimed", [
            _unimed(CPF_ANA, CPF_ANA, "ANA", "300.00"),
            _unimed(CPF_BRUNO, CPF_BRUNO, "BRUNO", "200.00"),
            _unimed("55555555555", "55555555555", "EX-COLAB", "-50.00"),
            _unimed("66666666666", "66666666666", "DESCONHECIDO", "40.00"),
        ])],
        [_colab(CPF_ANA, "ANA"), _colab(CPF_BRUNO, "BRUNO")],
    )


def test_totais_fecham_com_o_faturado_da_planilha() -> None:
    resultado = _cenario_misto()
    (totais,) = resultado.totais
    assert (totais.rateado, totais.estornos, totais.nao_rateado) == (
        Decimal("500.00"), Decimal("-50.00"), Decimal("40.00"),
    )
    assert totais.total == resultado.total_faturado_por_empresa["VERTEX"] == Decimal("490.00")

    (agregado,) = resultado.agregado  # mesmo CC: uma linha só para o ERP
    assert (agregado.valor, agregado.num_colaboradores) == (Decimal("500.00"), 2)


def test_reconciliacao_abate_estorno_e_acusa_o_nao_rateado() -> None:
    resultado = _cenario_misto()
    nf = DocumentoFatura(
        operadora="unimed", tipo="nf", nome_arquivo="nf.pdf",
        valor_total=Decimal("490.00"), empresa="Vertex",
    )
    (alerta,) = validators.reconciliar(resultado, [nf])
    # Valor final = rateado (500) + estorno (-50) = 450; a NF cobra 490: a
    # diferença é exatamente o titular não encontrado.
    assert alerta.valor_base == Decimal("450.00")
    assert (alerta.bate, alerta.diferenca) == (False, Decimal("40.00"))


def test_reconciliacao_prefere_nf_ao_boleto_da_mesma_empresa() -> None:
    resultado = _calcular(
        [_planilha("unimed", [_unimed(CPF_ANA, CPF_ANA, "ANA", "300.00")])],
        [_colab(CPF_ANA, "ANA")],
    )
    nf = DocumentoFatura(operadora="unimed", tipo="nf", nome_arquivo="nf.pdf",
                         valor_total=Decimal("300.00"), empresa="Vertex", numero="987")
    boleto = DocumentoFatura(operadora="unimed", tipo="boleto", nome_arquivo="b.pdf",
                             valor_total=Decimal("300.00"), empresa="Vertex")
    # Nas duas ordens: a NF carrega o número usado na pré-nota e no e-mail.
    for documentos in ([nf, boleto], [boleto, nf]):
        (alerta,) = validators.reconciliar(resultado, documentos)
        assert alerta.bate and alerta.numero_documento == "987"
