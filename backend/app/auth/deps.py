"""
Dependências de autenticação para o FastAPI.

`usuario_atual` lê o token Bearer do header Authorization, valida e devolve o
usuário (email, nome, areas, niveis). Rotas protegidas declaram
`usuario: dict = Depends(usuario_atual)`.
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth import service
from app.db.session import get_db
from app.services import organizacao

# tokenUrl relativo à raiz — casa com POST /api/auth/login (o botão Authorize
# do Swagger usa este endpoint).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


def usuario_atual(token: str = Depends(oauth2_scheme)) -> dict:
    try:
        return service.usuario_do_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def usuario_admin(usuario: dict = Depends(usuario_atual)) -> dict:
    """Exige que o usuário seja admin (vê tudo / gerencia cadastros)."""
    if "*" not in (usuario.get("areas") or []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requer permissão de administrador.",
        )
    return usuario


def exige_admin_area_do_tipo(tipo: str):
    """
    Dependência-fábrica: exige que o usuário seja admin_area (ou admin global) da
    área dona do rateio `tipo`. Usada nas ESCRITAS de cadastro por área (ex.:
    parâmetros da coparticipação).
    """

    def _dep(
        usuario: dict = Depends(usuario_atual), db: Session = Depends(get_db)
    ) -> dict:
        area_map = organizacao.mapa_areas_rateios(db)
        if not service.pode_auditar(
            usuario.get("areas") or [], usuario.get("niveis") or {}, tipo, area_map
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Requer admin_area da área responsável por este cadastro.",
            )
        return usuario

    return _dep


def usuario_admin_area(usuario: dict = Depends(usuario_atual)) -> dict:
    """
    Exige admin_area de QUALQUER área (ou admin global). Para cadastros de
    infraestrutura compartilhada entre rateios (ex.: centros de custo), que não
    pertencem a um único tipo.
    """
    if not service.eh_admin_area_qualquer(
        usuario.get("areas") or [], usuario.get("niveis") or {}
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requer permissão de administrador de área.",
        )
    return usuario
