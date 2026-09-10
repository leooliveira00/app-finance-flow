"""
Cadastro de EMPRESAS do grupo (fonte única do rateio de pagamento).

- GET    /api/cadastro/empresas        -> lista (autenticado)
- POST   /api/cadastro/empresas        -> cria (admin)
- PUT    /api/cadastro/empresas/{id}   -> atualiza (admin)
- DELETE /api/cadastro/empresas/{id}   -> remove (admin)

Campos: rótulo, `rest` do Protheus, CNPJ próprio (tomador), rotina de lançamento
no ERP ("ae"/"pre_nota") e constantes de pré-nota. Migrado do config.py/validators.
Obs.: a detecção de empresa por CNPJ na reconciliação (validators) é atualizada no
restart do backend; o rateio/ERP já lê do banco a cada requisição.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import usuario_admin_area, usuario_atual
from app.db.session import get_db
from app.models.organizacao_fiscal import Empresa

router = APIRouter(prefix="/cadastro/empresas", tags=["cadastro"])


class EmpresaIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    rest: str = ""
    cnpj: str = ""
    rotina_erp: str = "ae"
    prenota_produto: str = ""
    prenota_filial: str = ""


def _dict(e: Empresa) -> dict:
    return {
        "id": e.id, "nome": e.nome, "rest": e.rest, "cnpj": e.cnpj,
        "rotina_erp": e.rotina_erp,
        "prenota_produto": e.prenota_produto, "prenota_filial": e.prenota_filial,
    }


def _aplicar(e: Empresa, body: EmpresaIn) -> None:
    e.nome = body.nome.strip()
    e.rest = body.rest.strip()
    e.cnpj = body.cnpj.strip()
    e.rotina_erp = (body.rotina_erp or "ae").strip().lower()
    e.prenota_produto = body.prenota_produto.strip()
    e.prenota_filial = body.prenota_filial.strip()


@router.get("")
def listar(db: Session = Depends(get_db), _usuario: dict = Depends(usuario_atual)) -> list[dict]:
    return [_dict(e) for e in db.scalars(select(Empresa).order_by(Empresa.nome)).all()]


@router.post("", status_code=status.HTTP_201_CREATED)
def criar(body: EmpresaIn, db: Session = Depends(get_db), _adm: dict = Depends(usuario_admin_area)) -> dict:
    empresa = Empresa()
    _aplicar(empresa, body)
    db.add(empresa)
    try:
        db.commit()
        db.refresh(empresa)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Já existe uma empresa com esse nome.") from exc
    return _dict(empresa)


@router.put("/{empresa_id}")
def atualizar(empresa_id: int, body: EmpresaIn, db: Session = Depends(get_db), _adm: dict = Depends(usuario_admin_area)) -> dict:
    empresa = db.get(Empresa, empresa_id)
    if empresa is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    _aplicar(empresa, body)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Já existe uma empresa com esse nome.") from exc
    return _dict(empresa)


@router.delete("/{empresa_id}")
def remover(empresa_id: int, db: Session = Depends(get_db), _adm: dict = Depends(usuario_admin_area)) -> dict:
    empresa = db.get(Empresa, empresa_id)
    if empresa is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    db.delete(empresa)
    db.commit()
    return {"removido": True}
