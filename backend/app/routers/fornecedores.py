"""
Cadastro de FORNECEDORES dos lançamentos no ERP.

- GET    /api/cadastro/fornecedores        -> lista (autenticado)
- POST   /api/cadastro/fornecedores        -> cria (admin)
- PUT    /api/cadastro/fornecedores/{id}   -> atualiza (admin)
- DELETE /api/cadastro/fornecedores/{id}   -> remove (admin)

Campos: `nome` (a chave de negócio minúscula que o módulo de rateio declara em
`RateioModule.fornecedor` — "unimed", "bradesco", "claro") e `cnpj` (formatado;
no ERP vão só os dígitos, derivados). Era `/cadastro/operadoras`: o nome antigo
descrevia só o caso do plano de saúde, mas a entidade é a mesma na telefonia.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import usuario_admin_area, usuario_atual
from app.db.session import get_db
from app.models.organizacao_fiscal import Fornecedor

router = APIRouter(prefix="/cadastro/fornecedores", tags=["cadastro"])


class FornecedorIn(BaseModel):
    nome: str = Field(min_length=1, max_length=40)
    cnpj: str = ""


def _dict(f: Fornecedor) -> dict:
    return {"id": f.id, "nome": f.nome, "cnpj": f.cnpj}


def _aplicar(f: Fornecedor, body: FornecedorIn) -> None:
    f.nome = body.nome.strip().lower()
    f.cnpj = body.cnpj.strip()


@router.get("")
def listar(db: Session = Depends(get_db), _usuario: dict = Depends(usuario_atual)) -> list[dict]:
    return [_dict(f) for f in db.scalars(select(Fornecedor).order_by(Fornecedor.nome)).all()]


@router.post("", status_code=status.HTTP_201_CREATED)
def criar(body: FornecedorIn, db: Session = Depends(get_db), _adm: dict = Depends(usuario_admin_area)) -> dict:
    fornecedor = Fornecedor()
    _aplicar(fornecedor, body)
    db.add(fornecedor)
    try:
        db.commit()
        db.refresh(fornecedor)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Já existe um fornecedor com esse nome.") from exc
    return _dict(fornecedor)


@router.put("/{fornecedor_id}")
def atualizar(fornecedor_id: int, body: FornecedorIn, db: Session = Depends(get_db), _adm: dict = Depends(usuario_admin_area)) -> dict:
    fornecedor = db.get(Fornecedor, fornecedor_id)
    if fornecedor is None:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado.")
    _aplicar(fornecedor, body)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Já existe um fornecedor com esse nome.") from exc
    return _dict(fornecedor)


@router.delete("/{fornecedor_id}")
def remover(fornecedor_id: int, db: Session = Depends(get_db), _adm: dict = Depends(usuario_admin_area)) -> dict:
    fornecedor = db.get(Fornecedor, fornecedor_id)
    if fornecedor is None:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado.")
    db.delete(fornecedor)
    db.commit()
    return {"removido": True}
