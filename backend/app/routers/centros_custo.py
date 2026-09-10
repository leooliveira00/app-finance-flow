"""
Cadastro de centros de custo (código -> nome amigável) do rateio de pagamento.

- GET    /api/cadastro/centros-custo        -> lista (autenticado)
- POST   /api/cadastro/centros-custo        -> cria (admin)
- PUT    /api/cadastro/centros-custo/{id}   -> atualiza (admin)
- DELETE /api/cadastro/centros-custo/{id}   -> remove (admin)

Não é fonte de dados contábeis: apenas nomeia códigos para exibição e alimenta
o seletor ao atribuir um PJ a um centro de custo.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import usuario_admin_area, usuario_atual
from app.db.session import get_db
from app.models.pagamento import CentroCusto

router = APIRouter(prefix="/cadastro/centros-custo", tags=["cadastro"])


class CentroCustoIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=60)
    nome: str = Field(min_length=1, max_length=160)
    empresa: str = ""


def _dict(c: CentroCusto) -> dict:
    return {"id": c.id, "codigo": c.codigo, "nome": c.nome, "empresa": c.empresa}


@router.get("")
def listar(
    db: Session = Depends(get_db), _usuario: dict = Depends(usuario_atual)
) -> list[dict]:
    centros = db.scalars(select(CentroCusto).order_by(CentroCusto.nome)).all()
    return [_dict(c) for c in centros]


@router.post("", status_code=status.HTTP_201_CREATED)
def criar(
    body: CentroCustoIn, db: Session = Depends(get_db), _adm: dict = Depends(usuario_admin_area)
) -> dict:
    try:
        centro = CentroCusto(codigo=body.codigo.strip(), nome=body.nome.strip(), empresa=body.empresa.strip())
        db.add(centro)
        db.commit()
        db.refresh(centro)
        return _dict(centro)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Já existe um centro de custo com esse código.") from exc


@router.put("/{centro_id}")
def atualizar(
    centro_id: int,
    body: CentroCustoIn,
    db: Session = Depends(get_db),
    _adm: dict = Depends(usuario_admin_area),
) -> dict:
    centro = db.get(CentroCusto, centro_id)
    if centro is None:
        raise HTTPException(status_code=404, detail="Centro de custo não encontrado.")
    centro.codigo = body.codigo.strip()
    centro.nome = body.nome.strip()
    centro.empresa = body.empresa.strip()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Já existe um centro de custo com esse código.") from exc
    return _dict(centro)


@router.delete("/{centro_id}")
def remover(
    centro_id: int, db: Session = Depends(get_db), _adm: dict = Depends(usuario_admin_area)
) -> dict:
    centro = db.get(CentroCusto, centro_id)
    if centro is None:
        raise HTTPException(status_code=404, detail="Centro de custo não encontrado.")
    db.delete(centro)
    db.commit()
    return {"removido": True}
