"""
Leitura dos cadastros (Postgres) para compor `dados_externos` dos módulos.

`carregar_consenso` monta o consenso da coparticipação (faixas + valores + teto)
no formato que o `calculator` do módulo espera. Mantém o módulo puro: o router
carrega daqui e injeta em `dados_externos["consenso"]`.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.colaborador_demo import ColaboradorDemo
from app.models.coparticipacao import ColaboradorPJ, FaixaCoparticipacao, ParametroRateio
from app.models.pagamento import CentroCusto
from app.models.telefonia import LinhaTelefonica


def carregar_consenso(db: Session) -> dict[str, Any]:
    teto = db.get(ParametroRateio, "teto_percentual_copart")
    faixas = db.scalars(
        select(FaixaCoparticipacao).order_by(FaixaCoparticipacao.ordem)
    ).all()
    return {
        "teto_percentual": Decimal(teto.valor) if teto else Decimal("20"),
        "faixas": [
            {
                "nome": f.nome,
                "salario_inicial": f.salario_inicial,
                "salario_final": f.salario_final,
                "valores": {v.tipo: v.valor for v in f.valores},
            }
            for f in faixas
        ],
    }


def carregar_pj(db: Session) -> dict[str, Any]:
    """
    Cadastro de PJ para os módulos:
    - `cpfs` + `salario_padrao`: coparticipação (faixa por salário fixo).
    - `mapa`: pagamento — por CPF, a alocação contábil (centro de custo/empresa/
      classe) atribuída manualmente ao PJ. `nome` ajuda o casamento do Bradesco.
    """
    salario = db.get(ParametroRateio, "salario_padrao_pj")
    pjs = db.scalars(select(ColaboradorPJ)).all()
    return {
        "cpfs": [p.cpf for p in pjs],
        "salario_padrao": Decimal(salario.valor) if salario else Decimal("10000"),
        "mapa": {
            p.cpf: {
                "nome": p.nome,
                "centro_custo": p.centro_custo,
                "empresa": p.empresa,
                "classe_valor": p.classe_valor,
            }
            for p in pjs
        },
    }


# Contas contábeis da telefonia — fixas para todo o processo (não variam por
# linha nem por centro de custo), guardadas em `parametro_rateio`.
PARAM_TELEFONIA_CONTA_DEBITO = "telefonia_conta_debito"
PARAM_TELEFONIA_CONTA_CREDITO = "telefonia_conta_credito"


def carregar_linhas_telefonicas(db: Session) -> dict[str, dict[str, Any]]:
    """
    Cadastro de telefonia indexado pelo número (só dígitos), como o parser do
    boleto entrega. Alimenta `dados_externos["linhas_telefonicas"]`: é o de-para
    linha -> centro de custo usado pelo módulo da Claro.
    """
    linhas = db.scalars(select(LinhaTelefonica)).all()
    return {
        l.numero: {
            "centro_custo": l.centro_custo,
            "classe_valor": l.classe_valor,
            "conta": l.conta,
            "colaborador_cpf": l.colaborador_cpf,
            "colaborador_nome": l.colaborador_nome,
            "ativo": l.ativo,
            "observacao": l.observacao,
        }
        for l in linhas
    }


def carregar_parametros_telefonia(db: Session) -> dict[str, str]:
    """Contas de débito/crédito da telefonia (vazias enquanto não cadastradas)."""
    debito = db.get(ParametroRateio, PARAM_TELEFONIA_CONTA_DEBITO)
    credito = db.get(ParametroRateio, PARAM_TELEFONIA_CONTA_CREDITO)
    return {
        "conta_debito": debito.valor if debito else "",
        "conta_credito": credito.valor if credito else "",
    }


def carregar_colaboradores_demo(db: Session) -> list[dict[str, Any]]:
    """
    Cadastro fictício de colaboradores, usado no lugar do Protheus quando
    `PROTHEUS_READ_BASE_URL` está vazia (ver `colaborador_demo.py` e o router).

    Mesmo formato de dict que `protheus.listar_colaboradores` devolve, para os
    calculators (coparticipação e mensalidade) não precisarem saber a origem.
    """
    colaboradores = db.scalars(select(ColaboradorDemo)).all()
    return [
        {
            "cpf": c.cpf,
            "nome": c.nome,
            "salario": c.salario,
            "matricula": c.matricula,
            "filial": c.filial,
            "empresa": c.empresa,
            "situacao": c.situacao,
            "centro_custo": c.centro_custo,
            "classe_valor": c.classe_valor,
        }
        for c in colaboradores
    ]


def carregar_centros_custo(db: Session) -> list[dict[str, str]]:
    """Dicionário código -> nome dos centros de custo (exibição e seletor)."""
    centros = db.scalars(select(CentroCusto).order_by(CentroCusto.nome)).all()
    return [
        {"codigo": c.codigo, "nome": c.nome, "empresa": c.empresa} for c in centros
    ]
