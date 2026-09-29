"""
Coparticipação — desconto em folha: `calculator` e payload do ERP (`export_erp`).

Cobre as regras de negócio documentadas no CLAUDE.md que, erradas, descontam
valor indevido do colaborador: faixa por salário, teto da PESSOA (não do plano),
PJ, desligado, salário zerado, transferência ambígua no grupo e a consolidação
de quem tem dois planos num lançamento único por matrícula.

Os eventos entram já como `EventoCoparticipacao` (saída do parser): o layout das
planilhas das operadoras é outra responsabilidade.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.modules.coparticipacao import calculator, export_erp
from app.modules.coparticipacao.calculator import ResultadoCoparticipacao
from app.modules.coparticipacao.parser import Consolidado, EventoCoparticipacao

CPF_ANA = "11111111111"
CPF_BRUNO = "22222222222"

# Tabela de consenso: duas faixas de salário, valor FIXO por tipo de exame.
CONSENSO: dict[str, Any] = {
    "teto_percentual": 20,
    "faixas": [
        {
            "nome": "Faixa 1",
            "salario_inicial": 0,
            "salario_final": 3000,
            "valores": {"consulta": "10.00", "simples": "5.00", "especial": "30.00"},
        },
        {
            "nome": "Faixa 2",
            "salario_inicial": "3000.01",
            "salario_final": 100000,
            "valores": {"consulta": "20.00", "simples": "8.00", "especial": "50.00"},
        },
    ],
}


def _evento(cpf: str, tipo: str | None, operadora: str = "unimed",
            procedimento: str = "PROC") -> EventoCoparticipacao:
    return EventoCoparticipacao(
        cpf_titular=cpf, nome_titular="TITULAR " + cpf[-2:], nome_beneficiario="BENEF",
        tipo=tipo, procedimento=procedimento, valor_coparticipacao=Decimal("99"),
        data_atendimento=None, operadora=operadora,
    )


def _colab(cpf: str, salario: Any, **extra: Any) -> dict[str, Any]:
    return {
        "cpf": cpf, "nome": "NOME " + cpf[-2:], "salario": salario,
        "matricula": "000" + cpf[-3:], "filial": "01", "empresa": "Vertex",
        "situacao": "Situacao Normal", **extra,
    }


def _calcular(eventos: list[EventoCoparticipacao], colaboradores: list[dict[str, Any]],
              pj: dict[str, Any] | None = None) -> ResultadoCoparticipacao:
    return calculator.calcular(
        [Consolidado(nome_arquivo="c.xlsx", eventos=eventos)],
        {"colaboradores": colaboradores, "consenso": CONSENSO, "pj": pj or {}},
    )


# ---------------------------------------------------------------------------
# Faixa e precificação
# ---------------------------------------------------------------------------
def test_preco_e_fixo_por_faixa_e_tipo_de_exame() -> None:
    eventos = [_evento(CPF_ANA, "consulta"), _evento(CPF_ANA, "consulta"),
               _evento(CPF_ANA, "especial")]
    faixa1 = _calcular(eventos, [_colab(CPF_ANA, 2500)])
    faixa2 = _calcular(eventos, [_colab(CPF_ANA, 5000)])

    (item1,) = faixa1.itens
    assert (item1.faixa, item1.valor_descontado, item1.num_eventos) == (
        "Faixa 1", Decimal("50.00"), 3,
    )
    assert item1.por_tipo == {"consulta": "20.00", "simples": "0", "especial": "30.00"}
    # Mesmo eventos, faixa maior: a tabela muda, não a cobrança da operadora.
    assert faixa2.itens[0].valor_descontado == Decimal("90.00")
    assert faixa1.total_descontado == Decimal("50.00")


def test_procedimento_nao_classificado_vira_divergencia_sem_preco() -> None:
    resultado = _calcular(
        [_evento(CPF_ANA, "consulta"), _evento(CPF_ANA, None, procedimento="EXAME X")],
        [_colab(CPF_ANA, 2500)],
    )
    (item,) = resultado.itens
    assert (item.num_eventos, item.valor_descontado) == (1, Decimal("10.00"))
    (divergencia,) = resultado.divergencias
    assert divergencia.tipo == "procedimento_nao_classificado"
    assert "EXAME X" in divergencia.descricao


def test_salario_fora_das_faixas_vira_divergencia() -> None:
    consenso_curto = {**CONSENSO, "faixas": CONSENSO["faixas"][:1]}
    resultado = calculator.calcular(
        [Consolidado(nome_arquivo="c.xlsx", eventos=[_evento(CPF_ANA, "consulta")])],
        {"colaboradores": [_colab(CPF_ANA, 9000)], "consenso": consenso_curto},
    )
    assert resultado.itens == []
    assert [d.tipo for d in resultado.divergencias] == ["sem_faixa"]


# ---------------------------------------------------------------------------
# Teto: da PESSOA, sobre a soma dos planos
# ---------------------------------------------------------------------------
def test_dois_planos_abaixo_do_teto_geram_um_item_por_operadora() -> None:
    resultado = _calcular(
        [_evento(CPF_ANA, "consulta", "unimed"), _evento(CPF_ANA, "especial", "bradesco")],
        [_colab(CPF_ANA, 2500)],  # teto = 20% de 2500 = 500
    )
    por_operadora = {i.operadora: i for i in resultado.itens}
    assert set(por_operadora) == {"unimed", "bradesco"}
    assert por_operadora["unimed"].valor_descontado == Decimal("10.00")
    assert por_operadora["bradesco"].valor_descontado == Decimal("30.00")
    assert not any(i.teto_aplicado or i.bloqueado_envio for i in resultado.itens)


def test_teto_considera_a_soma_dos_planos_e_bloqueia_o_envio() -> None:
    # Salário 200 -> teto R$ 40. Cada plano sozinho (R$ 30) cabe no teto; a soma
    # (R$ 60) não. Teto por plano deixaria passar R$ 60, o dobro do permitido.
    resultado = _calcular(
        [_evento(CPF_ANA, "especial", "unimed"), _evento(CPF_ANA, "especial", "bradesco")],
        [_colab(CPF_ANA, 200)],
    )
    assert len(resultado.itens) == 2
    for item in resultado.itens:
        assert item.teto == Decimal("40.00")
        assert item.teto_aplicado and item.bloqueado_envio
        assert "Teto" in item.motivo_bloqueio
        assert item.valor_descontado == Decimal("20.00")  # parte proporcional do teto
    assert sum(i.valor_descontado for i in resultado.itens) == Decimal("40.00")
    assert any("teto" in aviso for aviso in resultado.avisos)


def test_valor_igual_ao_teto_nao_bloqueia() -> None:
    # Teto de R$ 30 (20% de 150) e bruto de R$ 30: "atingir" é ULTRAPASSAR.
    (item,) = _calcular([_evento(CPF_ANA, "especial")], [_colab(CPF_ANA, 150)]).itens
    assert not item.teto_aplicado and not item.bloqueado_envio


# ---------------------------------------------------------------------------
# Quem fica fora do rateio ou do lançamento automático
# ---------------------------------------------------------------------------
def test_pj_usa_salario_padrao_e_fica_fora_do_envio() -> None:
    resultado = _calcular(
        [_evento(CPF_BRUNO, "consulta")], [],
        pj={"cpfs": [CPF_BRUNO], "salario_padrao": 10000},
    )
    (item,) = resultado.itens
    assert item.pj and item.bloqueado_envio
    assert (item.empresa, item.faixa, item.salario) == ("PJ", "Faixa 2", Decimal("10000"))
    assert "PJ" in item.motivo_bloqueio


def test_titular_ausente_desligado_ou_sem_salario_nao_gera_item() -> None:
    cpf_ausente, cpf_demitido, cpf_zerado = "33333333333", "44444444444", "55555555555"
    resultado = _calcular(
        [_evento(cpf_ausente, "consulta"), _evento(cpf_demitido, "consulta"),
         _evento(cpf_zerado, "consulta")],
        [_colab(cpf_demitido, 2500, situacao="Demitido"), _colab(cpf_zerado, 0)],
    )
    assert resultado.itens == []
    assert resultado.total_descontado == Decimal("0")
    assert {d.cpf: d.tipo for d in resultado.divergencias} == {
        cpf_ausente: "titular_nao_encontrado",
        cpf_demitido: "colaborador_desligado",
        # Sem salário não há faixa: passar geraria um desconto de R$ 0,00 "válido".
        cpf_zerado: "sem_salario",
    }


def test_transferencia_ambigua_no_grupo_fica_fora_do_envio() -> None:
    colab = _colab(CPF_ANA, 2500, **{calculator.CHAVE_AMBIGUIDADE: ["Vertex/000111",
                                                                     "Zenith/000999"]})
    resultado = _calcular([_evento(CPF_ANA, "consulta")], [colab])

    (item,) = resultado.itens
    assert item.bloqueado_envio and not item.teto_aplicado and not item.pj
    assert "Zenith/000999" in item.motivo_bloqueio
    assert any("equivalente" in aviso for aviso in resultado.avisos)


# ---------------------------------------------------------------------------
# Payload do ERP (rotina GPE)
# ---------------------------------------------------------------------------
def _snapshot(resultado: ResultadoCoparticipacao) -> list[dict[str, Any]]:
    """Itens como ficam no snapshot da execução (Decimal serializado em string)."""
    return [
        {**vars(i), "valor_descontado": str(i.valor_descontado)} for i in resultado.itens
    ]


def test_payload_consolida_dois_planos_numa_entrada_por_matricula() -> None:
    resultado = _calcular(
        [_evento(CPF_ANA, "consulta", "unimed"), _evento(CPF_ANA, "especial", "bradesco"),
         _evento(CPF_BRUNO, "simples", "bradesco")],
        [_colab(CPF_ANA, 2500), _colab(CPF_BRUNO, 2500)],
    )
    payload = export_erp.gerar(_snapshot(resultado), "202608", "20260806")

    por_matricula = {e["HEADER"]["RA_MAT"]: e["ITENS"] for e in payload}
    assert set(por_matricula) == {"000111", "000222"}

    (ana,) = por_matricula["000111"]  # dois planos -> UM lançamento, valores somados
    assert (ana["RHO_VLRFUN"], ana["RHO_CODFOR"]) == (40.0, "07")
    assert (ana["RHO_COMPPG"], ana["RHO_DTOCOR"], ana["RHO_CPF"]) == (
        "202608", "20260806", CPF_ANA,
    )
    (bruno,) = por_matricula["000222"]  # um plano mantém o código dele
    assert (bruno["RHO_VLRFUN"], bruno["RHO_CODFOR"]) == (5.0, "03")


def test_payload_exclui_bloqueados_e_respeita_filtros() -> None:
    resultado = _calcular(
        [_evento(CPF_ANA, "consulta"), _evento(CPF_BRUNO, "consulta"),
         _evento("66666666666", "especial"), _evento("66666666666", "especial")],
        [_colab(CPF_ANA, 2500), _colab(CPF_BRUNO, 2500, empresa="Zenith"),
         _colab("66666666666", 200)],  # teto R$ 40 < R$ 60: bloqueado
    )
    itens = _snapshot(resultado)

    todos = export_erp.gerar(itens, "202608", "20260806")
    assert {e["HEADER"]["RA_MAT"] for e in todos} == {"000111", "000222"}

    so_zenith = export_erp.gerar(itens, "202608", "20260806", empresa="ZENITH")
    assert [e["HEADER"]["RA_MAT"] for e in so_zenith] == ["000222"]

    # Reenvio seletivo: só as matrículas recusadas voltam ao ERP.
    reenvio = export_erp.gerar(itens, "202608", "20260806", matriculas={"000111"})
    assert [e["HEADER"]["RA_MAT"] for e in reenvio] == ["000111"]


def test_elegivel_respeita_snapshot_antigo_sem_marca_de_bloqueio() -> None:
    base = {"matricula": "000111", "filial": "01", "valor_descontado": "10.00"}
    assert export_erp.elegivel(base)
    # Snapshots anteriores a `bloqueado_envio` só têm pj/teto_aplicado.
    assert not export_erp.elegivel({**base, "pj": True})
    assert not export_erp.elegivel({**base, "teto_aplicado": True})
    assert not export_erp.elegivel({**base, "filial": ""})
    assert not export_erp.elegivel({**base, "valor_descontado": "0"})
