"""
Rotas de autenticação.

- POST /api/auth/login: e-mail/senha (form) -> JWT + dados do usuário.
- GET  /api/auth/me:    dados do usuário do token atual.
- PUT  /api/auth/me:    autogestão do próprio perfil (nome e/ou senha; NÃO o e-mail).

O prefixo /api é aplicado em main.py.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.deps import usuario_atual
from app.config import Settings, get_settings
from app.db.session import get_db
from app.services import organizacao

router = APIRouter(prefix="/auth", tags=["auth"])


class PerfilUpdate(BaseModel):
    nome: str | None = None
    senha_atual: str | None = None
    senha_nova: str | None = None


@router.post("/login")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Autentica por e-mail/senha e devolve o token + dados do usuário.

    O campo `username` do formulário OAuth2 carrega o e-mail (o login é por e-mail).
    """
    usuario = organizacao.autenticar(db, form.username, form.password)
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos.",
        )
    token = service.criar_token(usuario)
    return {
        "access_token": token,
        "token_type": "bearer",
        "email": usuario["email"],
        "nome": usuario["nome"],
        "areas": usuario["areas"],
        "niveis": usuario["niveis"],
        # Ambiente da base de ESCRITA do ERP: a UI marca a sessão enquanto os
        # lançamentos não vão para a base oficial (ver app/config.py).
        "erp_ambiente": settings.protheus_write_ambiente,
    }


@router.get("/me")
def me(
    usuario: dict = Depends(usuario_atual),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Retorna os dados do usuário autenticado (para o frontend restaurar sessão)."""
    return {**usuario, "erp_ambiente": settings.protheus_write_ambiente}


@router.put("/me")
def atualizar_me(
    body: PerfilUpdate,
    usuario: dict = Depends(usuario_atual),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Autogestão: o próprio usuário altera nome e/ou senha (o e-mail é imutável aqui)."""
    try:
        atualizado = organizacao.atualizar_perfil(
            db, usuario["email"], body.nome, body.senha_atual, body.senha_nova
        )
    except organizacao.SenhaAtualInvalida as exc:
        raise HTTPException(status_code=400, detail="A senha atual está incorreta.") from exc
    if atualizado is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    # Mesma forma de /login e GET /me: o frontend substitui a sessão por esta
    # resposta, então ela também carrega o ambiente do ERP.
    return {**atualizado, "erp_ambiente": settings.protheus_write_ambiente}
