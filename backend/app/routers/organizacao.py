"""
Organização: cadastro de usuários e áreas (setores) — todas admin-only.

- GET/POST/PUT/DELETE /api/organizacao/usuarios[/{id}]
- GET/POST/PUT/DELETE /api/organizacao/areas[/{id}]
- GET /api/organizacao/rateios  -> tipos de rateio disponíveis (para vincular às áreas)

A fonte de verdade é o Postgres (models.auth). O que for cadastrado aqui passa
a valer para login (autenticação) e para a segregação por área (autorização).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import usuario_admin
from app.db.session import get_db
from app.modules.registry import registry
from app.services import notificacao_config, organizacao

router = APIRouter(prefix="/organizacao", tags=["organizacao"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class AreaNivelIn(BaseModel):
    """Vínculo de uma área com o nível do usuário nela."""

    area: str = Field(min_length=1, max_length=60)
    nivel: str = "operador"  # operador | admin_area (normalizado no serviço)


class UsuarioIn(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    nome: str = Field(min_length=1, max_length=120)
    senha: str = Field(min_length=1)
    admin: bool = False
    areas: list[AreaNivelIn] = Field(default_factory=list)


class UsuarioUpdate(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=120)
    admin: bool = False
    ativo: bool = True
    areas: list[AreaNivelIn] = Field(default_factory=list)
    senha: str | None = None  # opcional: só troca se enviado


class AreaIn(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    rateios: list[str] = Field(default_factory=list)
    # E-mails em cópia nas notificações dos rateios desta área (lista separada
    # por vírgula). Vazio = as notificações vão só ao fiscal.
    emails_copia: str = Field(default="", max_length=500)


# ---------------------------------------------------------------------------
# Rateios disponíveis (para vincular às áreas)
# ---------------------------------------------------------------------------
def _nome_curto(m) -> str:
    """Nome curto do rateio; fallback a partir do tipo se o módulo não definir."""
    if getattr(m, "nome", ""):
        return m.nome
    return m.tipo.replace("-", " ").replace("_", " ").title()


@router.get("/rateios")
def listar_rateios(_adm: dict = Depends(usuario_admin)) -> list[dict]:
    return [
        {"tipo": m.tipo, "nome": _nome_curto(m), "descricao": m.descricao}
        for m in registry.list_modules()
    ]


# ---------------------------------------------------------------------------
# Usuários
# ---------------------------------------------------------------------------
@router.get("/usuarios")
def listar_usuarios(
    db: Session = Depends(get_db), _adm: dict = Depends(usuario_admin)
) -> list[dict]:
    return organizacao.listar_usuarios(db)


@router.post("/usuarios", status_code=status.HTTP_201_CREATED)
def criar_usuario(
    body: UsuarioIn, db: Session = Depends(get_db), _adm: dict = Depends(usuario_admin)
) -> dict:
    try:
        return organizacao.criar_usuario(
            db,
            body.email.strip(),
            body.nome.strip(),
            body.senha,
            body.admin,
            [a.model_dump() for a in body.areas],
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Já existe um usuário com esse e-mail.") from exc


@router.put("/usuarios/{usuario_id}")
def atualizar_usuario(
    usuario_id: int,
    body: UsuarioUpdate,
    db: Session = Depends(get_db),
    _adm: dict = Depends(usuario_admin),
) -> dict:
    try:
        resultado = organizacao.atualizar_usuario(
            db,
            usuario_id,
            body.nome.strip(),
            body.email.strip(),
            body.admin,
            body.ativo,
            [a.model_dump() for a in body.areas],
            body.senha,
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Já existe um usuário com esse e-mail.") from exc
    if resultado is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return resultado


@router.delete("/usuarios/{usuario_id}")
def remover_usuario(
    usuario_id: int, db: Session = Depends(get_db), adm: dict = Depends(usuario_admin)
) -> dict:
    removido = organizacao.remover_usuario(db, usuario_id)
    if not removido:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return {"removido": True}


# ---------------------------------------------------------------------------
# Áreas (setores)
# ---------------------------------------------------------------------------
def _validar_emails(valor: str) -> None:
    """Formato dos e-mails de cópia: recusa no CADASTRO, não no envio.

    Um endereço malformado descoberto na hora de notificar deixaria o rateio já
    lançado no ERP e o fiscal sem aviso.
    """
    ruins = notificacao_config.invalidos(valor)
    if ruins:
        raise HTTPException(status_code=422, detail="E-mail inválido: " + ", ".join(ruins))



@router.get("/areas")
def listar_areas(
    db: Session = Depends(get_db), _adm: dict = Depends(usuario_admin)
) -> list[dict]:
    return organizacao.listar_areas(db)


@router.post("/areas", status_code=status.HTTP_201_CREATED)
def criar_area(
    body: AreaIn, db: Session = Depends(get_db), _adm: dict = Depends(usuario_admin)
) -> dict:
    _validar_emails(body.emails_copia)
    try:
        return organizacao.criar_area(
            db, body.nome.strip(), body.rateios, body.emails_copia.strip()
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Já existe uma área com esse nome.") from exc


@router.put("/areas/{area_id}")
def atualizar_area(
    area_id: int,
    body: AreaIn,
    db: Session = Depends(get_db),
    _adm: dict = Depends(usuario_admin),
) -> dict:
    _validar_emails(body.emails_copia)
    resultado = organizacao.atualizar_area(
        db, area_id, body.nome.strip(), body.rateios, body.emails_copia.strip()
    )
    if resultado is None:
        raise HTTPException(status_code=404, detail="Área não encontrada.")
    return resultado


@router.delete("/areas/{area_id}")
def remover_area(
    area_id: int, db: Session = Depends(get_db), _adm: dict = Depends(usuario_admin)
) -> dict:
    removido = organizacao.remover_area(db, area_id)
    if not removido:
        raise HTTPException(status_code=404, detail="Área não encontrada.")
    return {"removido": True}
