"""
Destinatários institucionais das notificações (admin).

- GET /api/notificacoes                -> fiscal + cópia permanente
- PUT /api/notificacoes                -> altera os dois
- GET /api/notificacoes/destinatarios  -> prévia de quem receberá um rateio

A cópia da ÁREA responsável não é editada aqui: ela fica no cadastro da área
(Setores e permissões), porque a área é dona dos processos. A prévia existe para
a tela de confirmação mostrar, antes do envio, quem vai receber.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import usuario_admin, usuario_atual
from app.config import Settings, get_settings
from app.db.session import get_db
from app.services import notificacao_config

router = APIRouter(prefix="/notificacoes", tags=["notificacoes"])


class ConfigIn(BaseModel):
    fiscal_emails: str = ""
    copia_permanente: str = ""


def _dict(cfg) -> dict:
    return {
        "fiscal_emails": cfg.fiscal_emails,
        "copia_permanente": cfg.copia_permanente,
        "atualizado_por": cfg.atualizado_por,
        "atualizado_em": cfg.atualizado_em.isoformat() if cfg.atualizado_em else None,
    }


@router.get("")
def obter(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _adm: dict = Depends(usuario_admin),
) -> dict:
    return _dict(notificacao_config.obter_config(db, settings))


@router.put("")
def atualizar(
    body: ConfigIn,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    admin: dict = Depends(usuario_admin),
) -> dict:
    # Validação no CADASTRO: um endereço malformado descoberto no envio deixaria
    # o rateio lançado no ERP e o fiscal sem aviso.
    ruins = notificacao_config.invalidos(body.fiscal_emails) + notificacao_config.invalidos(
        body.copia_permanente
    )
    if ruins:
        raise HTTPException(
            status_code=422, detail="E-mail inválido: " + ", ".join(ruins)
        )
    cfg = notificacao_config.obter_config(db, settings)
    cfg.fiscal_emails = body.fiscal_emails.strip()
    cfg.copia_permanente = body.copia_permanente.strip()
    cfg.atualizado_por = admin.get("email", "")
    db.commit()
    db.refresh(cfg)
    return _dict(cfg)


@router.get("/destinatarios")
def destinatarios(
    tipo: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _usuario: dict = Depends(usuario_atual),
) -> dict:
    """Quem receberá a notificação deste rateio (prévia para a confirmação)."""
    return notificacao_config.resolver(db, settings, tipo)
