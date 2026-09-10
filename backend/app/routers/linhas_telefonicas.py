"""
Cadastro da telefonia: linhas e parâmetros contábeis do processo.

- GET    /api/cadastro/linhas-telefonicas             -> lista (autenticado)
- POST   /api/cadastro/linhas-telefonicas             -> cria
- POST   /api/cadastro/linhas-telefonicas/lote        -> cria/atualiza em massa
- PUT    /api/cadastro/linhas-telefonicas/{id}        -> atualiza
- DELETE /api/cadastro/linhas-telefonicas/{id}        -> remove
- GET    /api/cadastro/linhas-telefonicas/parametros  -> contas de débito/crédito
- PUT    /api/cadastro/linhas-telefonicas/parametros  -> grava as contas

O que é por LINHA (centro de custo, classe de valor, conta Claro, responsável)
fica na tabela; o que é FIXO do processo (conta de débito e de crédito, iguais
para toda a telefonia) fica em `parametro_rateio`. Assim o plano de contas muda
em um lugar só, em vez de em centenas de linhas.

Permissão das ESCRITAS: quem tem acesso ao rateio `pagamento-claro` — ou seja, a
área dona do processo (TI). Não exige admin de propósito: quando o boleto traz
uma linha nova, o operador precisa cadastrá-la ali mesmo, no alerta da prévia,
sem depender de um administrador.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import service as auth_service
from app.auth.deps import usuario_atual
from app.db.session import get_db
from app.models.coparticipacao import ParametroRateio
from app.models.telefonia import LinhaTelefonica
from app.modules.pagamento_claro.module import PagamentoClaroRateio
from app.services import organizacao
from app.services.cadastro import (
    PARAM_TELEFONIA_CONTA_CREDITO,
    PARAM_TELEFONIA_CONTA_DEBITO,
    carregar_parametros_telefonia,
)

router = APIRouter(prefix="/cadastro/linhas-telefonicas", tags=["cadastro"])


def _mantenedor(
    usuario: dict = Depends(usuario_atual), db: Session = Depends(get_db)
) -> dict:
    """Exige acesso ao rateio da Claro — a área dona do cadastro (TI)."""
    area_map = organizacao.mapa_areas_rateios(db)
    if not auth_service.pode_ver(usuario.get("areas") or [], PagamentoClaroRateio.tipo, area_map):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requer acesso ao processo de telefonia (área de TI).",
        )
    return usuario


class LinhaIn(BaseModel):
    numero: str = Field(min_length=8, max_length=20)
    # Centro de custo e classe de valor são OBRIGATÓRIOS: o ERP rejeita o
    # lançamento com qualquer um dos dois em branco.
    centro_custo: str = Field(min_length=1, max_length=60)
    classe_valor: str = Field(min_length=1, max_length=60)
    conta: str = ""
    colaborador_cpf: str = ""
    colaborador_nome: str = ""
    ativo: bool = True
    observacao: str = ""

    @field_validator("numero", "colaborador_cpf")
    @classmethod
    def _so_digitos(cls, valor: str) -> str:
        """Número e CPF são gravados sem máscara — é como o boleto é lido."""
        return re.sub(r"\D", "", valor or "")


def _dict(l: LinhaTelefonica) -> dict:
    return {
        "id": l.id,
        "numero": l.numero,
        "centro_custo": l.centro_custo,
        "classe_valor": l.classe_valor,
        "conta": l.conta,
        "colaborador_cpf": l.colaborador_cpf,
        "colaborador_nome": l.colaborador_nome,
        "ativo": l.ativo,
        "observacao": l.observacao,
    }


def _aplicar(linha: LinhaTelefonica, body: LinhaIn) -> None:
    linha.numero = body.numero
    linha.centro_custo = body.centro_custo.strip()
    linha.classe_valor = body.classe_valor.strip()
    linha.conta = body.conta.strip()
    linha.colaborador_cpf = body.colaborador_cpf
    linha.colaborador_nome = body.colaborador_nome.strip()
    linha.ativo = body.ativo
    linha.observacao = body.observacao.strip()


@router.get("")
def listar(
    db: Session = Depends(get_db), _usuario: dict = Depends(usuario_atual)
) -> list[dict]:
    linhas = db.scalars(select(LinhaTelefonica).order_by(LinhaTelefonica.numero)).all()
    return [_dict(l) for l in linhas]


@router.post("", status_code=status.HTTP_201_CREATED)
def criar(
    body: LinhaIn, db: Session = Depends(get_db), _mant: dict = Depends(_mantenedor)
) -> dict:
    linha = LinhaTelefonica()
    _aplicar(linha, body)
    db.add(linha)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Essa linha já está cadastrada.") from exc
    db.refresh(linha)
    return _dict(linha)


@router.post("/lote")
def criar_em_lote(
    body: list[LinhaIn], db: Session = Depends(get_db), _mant: dict = Depends(_mantenedor)
) -> dict:
    """
    Importa várias linhas de uma vez (upsert por número).

    Existe porque o parque tem centenas de linhas espalhadas em vários boletos —
    cadastrar uma a uma na mão inviabilizaria a adoção. Número repetido no mesmo
    lote: vence a última ocorrência.
    """
    existentes = {
        l.numero: l for l in db.scalars(select(LinhaTelefonica)).all()
    }
    criadas, atualizadas = 0, 0
    for item in body:
        linha = existentes.get(item.numero)
        if linha is None:
            linha = LinhaTelefonica()
            db.add(linha)
            existentes[item.numero] = linha
            criadas += 1
        else:
            atualizadas += 1
        _aplicar(linha, item)
    db.commit()
    return {"criadas": criadas, "atualizadas": atualizadas}


class ParametrosIn(BaseModel):
    """Contas contábeis fixas da telefonia (iguais para todas as linhas)."""

    conta_debito: str = ""
    conta_credito: str = ""


# NOTA: declarado ANTES de "/{linha_id}" — o FastAPI casa as rotas na ordem, e
# "/parametros" cairia no path param inteiro (422) se viesse depois.
@router.get("/parametros")
def obter_parametros(
    db: Session = Depends(get_db), _usuario: dict = Depends(usuario_atual)
) -> dict:
    return carregar_parametros_telefonia(db)


@router.put("/parametros")
def salvar_parametros(
    body: ParametrosIn, db: Session = Depends(get_db), _mant: dict = Depends(_mantenedor)
) -> dict:
    descricoes = {
        PARAM_TELEFONIA_CONTA_DEBITO: "Conta contábil de DÉBITO da telefonia (despesa).",
        PARAM_TELEFONIA_CONTA_CREDITO: "Conta contábil de CRÉDITO da telefonia (fornecedor).",
    }
    valores = {
        PARAM_TELEFONIA_CONTA_DEBITO: body.conta_debito.strip(),
        PARAM_TELEFONIA_CONTA_CREDITO: body.conta_credito.strip(),
    }
    for chave, valor in valores.items():
        parametro = db.get(ParametroRateio, chave)
        if parametro is None:
            parametro = ParametroRateio(chave=chave, descricao=descricoes[chave])
            db.add(parametro)
        parametro.valor = valor
    db.commit()
    return carregar_parametros_telefonia(db)


@router.put("/{linha_id}")
def atualizar(
    linha_id: int,
    body: LinhaIn,
    db: Session = Depends(get_db),
    _mant: dict = Depends(_mantenedor),
) -> dict:
    linha = db.get(LinhaTelefonica, linha_id)
    if linha is None:
        raise HTTPException(status_code=404, detail="Linha não encontrada.")
    _aplicar(linha, body)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Essa linha já está cadastrada.") from exc
    return _dict(linha)


@router.delete("/{linha_id}")
def remover(
    linha_id: int, db: Session = Depends(get_db), _mant: dict = Depends(_mantenedor)
) -> dict:
    linha = db.get(LinhaTelefonica, linha_id)
    if linha is None:
        raise HTTPException(status_code=404, detail="Linha não encontrada.")
    db.delete(linha)
    db.commit()
    return {"removido": True}
