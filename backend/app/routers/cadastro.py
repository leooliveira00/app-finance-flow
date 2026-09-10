"""
Cadastro parametrizável da Coparticipação (faixas + valores + teto).

- GET  /api/cadastro/coparticipacao  -> retorna o cadastro atual (autenticado).
- PUT  /api/cadastro/coparticipacao  -> substitui todo o cadastro (admin).

A tela de cadastro edita/ cria faixas e envia o conjunto completo; o PUT
substitui as faixas numa transação (o teto é atualizado no parâmetro).
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import exige_admin_area_do_tipo, usuario_atual
from app.db.session import get_db
from app.models.coparticipacao import (
    ColaboradorPJ,
    FaixaCoparticipacao,
    ParametroRateio,
    ValorCoparticipacao,
)
from app.modules.coparticipacao.parser import normalizar_cpf

router = APIRouter(prefix="/cadastro/coparticipacao", tags=["cadastro"])

# Tipo do rateio dono deste cadastro; escrever exige admin_area desta área.
TIPO_COPARTICIPACAO = "coparticipacao-plano-saude"
_exige_copart_admin = exige_admin_area_do_tipo(TIPO_COPARTICIPACAO)

TIPOS = ("consulta", "simples", "especial")
_PARAM_TETO = "teto_percentual_copart"
_PARAM_PJ = "salario_padrao_pj"


class ValoresIn(BaseModel):
    consulta: Decimal = Field(ge=0)
    simples: Decimal = Field(ge=0)
    especial: Decimal = Field(ge=0)


class FaixaIn(BaseModel):
    nome: str
    salario_inicial: Decimal = Field(ge=0)
    salario_final: Decimal = Field(ge=0)
    valores: ValoresIn


class CadastroIn(BaseModel):
    teto_percentual: Decimal = Field(ge=0, le=100)
    salario_padrao_pj: Decimal = Field(ge=0)
    faixas: list[FaixaIn]


def _serializar(db: Session) -> dict:
    teto = db.get(ParametroRateio, _PARAM_TETO)
    pj_sal = db.get(ParametroRateio, _PARAM_PJ)
    faixas = db.scalars(
        select(FaixaCoparticipacao).order_by(FaixaCoparticipacao.ordem)
    ).all()
    return {
        "teto_percentual": str(teto.valor) if teto else "20",
        "salario_padrao_pj": str(pj_sal.valor) if pj_sal else "10000",
        "faixas": [
            {
                "nome": f.nome,
                "salario_inicial": str(f.salario_inicial),
                "salario_final": str(f.salario_final),
                "valores": {v.tipo: str(v.valor) for v in f.valores},
            }
            for f in faixas
        ],
    }


@router.get("")
def obter(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(usuario_atual),
) -> dict:
    return _serializar(db)


@router.put("")
def salvar(
    cadastro: CadastroIn,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(_exige_copart_admin),
) -> dict:
    """Substitui o cadastro inteiro (faixas + teto) numa transação."""
    teto = db.get(ParametroRateio, _PARAM_TETO)
    if teto is None:
        teto = ParametroRateio(
            chave=_PARAM_TETO,
            descricao="Teto do desconto de coparticipação (% do salário).",
        )
        db.add(teto)
    teto.valor = str(cadastro.teto_percentual)

    pj_sal = db.get(ParametroRateio, _PARAM_PJ)
    if pj_sal is None:
        pj_sal = ParametroRateio(
            chave=_PARAM_PJ, descricao="Salário padrão de colaboradores PJ (define a faixa)."
        )
        db.add(pj_sal)
    pj_sal.valor = str(cadastro.salario_padrao_pj)

    # Substitui todas as faixas (o FK ondelete=CASCADE remove os valores).
    db.query(FaixaCoparticipacao).delete()
    db.flush()
    for ordem, faixa in enumerate(cadastro.faixas):
        db.add(
            FaixaCoparticipacao(
                nome=faixa.nome,
                salario_inicial=faixa.salario_inicial,
                salario_final=faixa.salario_final,
                ordem=ordem,
                valores=[
                    ValorCoparticipacao(tipo=tipo, valor=getattr(faixa.valores, tipo))
                    for tipo in TIPOS
                ],
            )
        )
    db.commit()
    return _serializar(db)


# --------------------------------------------------------------------------
# Colaboradores PJ (cadastro especial: salário padrão, não busca na API)
# --------------------------------------------------------------------------
class PJIn(BaseModel):
    cpf: str
    nome: str = ""
    # Alocação contábil p/ o rateio de PAGAMENTO (opcional; só PJ). Enviado ao
    # atribuir um PJ a um centro de custo na tela de resultado do pagamento.
    centro_custo: str | None = None
    empresa: str | None = None
    classe_valor: str | None = None


def _pj_dict(p: ColaboradorPJ) -> dict:
    return {
        "cpf": p.cpf,
        "nome": p.nome,
        "centro_custo": p.centro_custo,
        "empresa": p.empresa,
        "classe_valor": p.classe_valor,
    }


@router.get("/pj")
def listar_pj(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(usuario_atual),
) -> list[dict]:
    linhas = db.scalars(select(ColaboradorPJ).order_by(ColaboradorPJ.nome)).all()
    return [_pj_dict(p) for p in linhas]


@router.post("/pj")
def adicionar_pj(
    pj: PJIn,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(_exige_copart_admin),
) -> dict:
    """
    Adiciona ou atualiza um colaborador PJ (idempotente por CPF). Campos de
    alocação (centro_custo/empresa/classe_valor) só são gravados quando enviados,
    preservando o que já existe caso venham nulos.
    """
    cpf = normalizar_cpf(pj.cpf)
    if not cpf:
        raise HTTPException(status_code=422, detail="CPF inválido.")
    obj = db.scalar(select(ColaboradorPJ).where(ColaboradorPJ.cpf == cpf))
    if obj is None:
        obj = ColaboradorPJ(cpf=cpf)
        db.add(obj)
    if pj.nome:
        obj.nome = pj.nome
    if pj.centro_custo is not None:
        obj.centro_custo = pj.centro_custo
    if pj.empresa is not None:
        obj.empresa = pj.empresa
    if pj.classe_valor is not None:
        obj.classe_valor = pj.classe_valor
    db.commit()
    return _pj_dict(obj)


@router.delete("/pj/{cpf}")
def remover_pj(
    cpf: str,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(_exige_copart_admin),
) -> dict:
    """Remove um colaborador do cadastro PJ (volta a ser buscado na API)."""
    alvo = normalizar_cpf(cpf)
    obj = db.scalar(select(ColaboradorPJ).where(ColaboradorPJ.cpf == alvo))
    if obj:
        db.delete(obj)
        db.commit()
    return {"cpf": alvo, "removido": obj is not None}
