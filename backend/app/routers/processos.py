"""
Administração da disponibilidade dos processos (rateios).

- GET /api/processos        -> todos os processos descobertos + status (admin)
- PUT /api/processos/{tipo} -> ativa/desativa um processo (admin)

Exige admin global (não admin de área): a disponibilidade de um processo vale
para a ferramenta inteira, não para uma área. Ver `models/processo.py` para o
que "inativo" significa.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import service as auth_service
from app.auth.deps import usuario_admin
from app.db.session import get_db
from app.modules.registry import registry
from app.services import organizacao, processos

router = APIRouter(prefix="/processos", tags=["processos"])


class StatusIn(BaseModel):
    ativo: bool


@router.get("")
def listar(
    db: Session = Depends(get_db), _adm: dict = Depends(usuario_admin)
) -> list[dict]:
    """Processos descobertos com nome, área e status (inclui os inativos)."""
    status = processos.listar(db)
    area_map = organizacao.mapa_areas_rateios(db)
    itens = []
    for modulo in registry.list_modules():
        linha = status.get(modulo.tipo)
        itens.append({
            "tipo": modulo.tipo,
            "nome": getattr(modulo, "nome", "") or modulo.tipo,
            "descricao": getattr(modulo, "descricao", ""),
            "area": auth_service.area_de_tipo(modulo.tipo, area_map) or "",
            "ativo": True if linha is None else linha.ativo,
            "atualizado_por": linha.atualizado_por if linha else "",
            "atualizado_em": linha.atualizado_em.isoformat() if linha and linha.atualizado_em else None,
        })
    return sorted(itens, key=lambda i: i["nome"])


@router.put("/{tipo}")
def definir(
    tipo: str,
    body: StatusIn,
    db: Session = Depends(get_db),
    admin: dict = Depends(usuario_admin),
) -> dict:
    """Ativa ou desativa o processo. Só aceita tipo de módulo existente."""
    if tipo not in {m.tipo for m in registry.list_modules()}:
        raise HTTPException(status_code=404, detail="Processo não encontrado.")
    linha = processos.definir_ativo(db, tipo, body.ativo, admin.get("email", ""))
    return {
        "tipo": linha.tipo,
        "ativo": linha.ativo,
        "atualizado_por": linha.atualizado_por,
        "atualizado_em": linha.atualizado_em.isoformat() if linha.atualizado_em else None,
    }
