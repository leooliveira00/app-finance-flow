"""
Resolução dos destinatários de uma notificação.

Regra única, consumida pelo envio e pela prévia exibida ao operador:

    Para   = fiscal (cadastro; na falta, o `.env`)
    Cópia  = cópia permanente + e-mails da ÁREA dona do rateio
    Reply-To = e-mails da área (a resposta do fiscal cai em quem tratou)

A cópia nunca impede o envio: área sem e-mail cadastrado notifica só o fiscal.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.auth import Area, AreaRateio
from app.models.notificacao import ConfigNotificacao

_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def lista(valor: str) -> list[str]:
    """Quebra uma lista separada por vírgula (ou ponto e vírgula), sem vazios."""
    return [e.strip() for e in re.split(r"[;,]", valor or "") if e.strip()]


def invalidos(valor: str) -> list[str]:
    """E-mails com formato inválido — validados no CADASTRO, não no envio."""
    return [e for e in lista(valor) if not _RE_EMAIL.match(e)]


def obter_config(db: Session, settings: Settings) -> ConfigNotificacao:
    """
    Config de notificação, criada na primeira leitura a partir do `.env`.

    Assim a migração do `.env` para o cadastro é transparente: quem já tinha
    `FISCAL_EMAILS` continua notificando os mesmos endereços.
    """
    cfg = db.get(ConfigNotificacao, 1)
    if cfg is None:
        cfg = ConfigNotificacao(id=1, fiscal_emails=settings.fiscal_emails or "")
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def _emails_da_area_do_tipo(db: Session, tipo: str) -> list[str]:
    area = db.scalar(
        select(Area).join(AreaRateio, AreaRateio.area_id == Area.id).where(AreaRateio.tipo == tipo)
    )
    return lista(area.emails_copia) if area else []


def resolver(db: Session, settings: Settings, tipo: str) -> dict[str, list[str]]:
    """Destinatários da notificação do rateio `tipo`: {para, copia, reply_to}."""
    cfg = obter_config(db, settings)
    para = lista(cfg.fiscal_emails) or settings.lista_fiscal()
    area = _emails_da_area_do_tipo(db, tipo)
    # `dict.fromkeys` remove repetidos preservando a ordem: um e-mail que esteja
    # na cópia permanente e também na área apareceria duas vezes no cabeçalho.
    copia = list(dict.fromkeys([*lista(cfg.copia_permanente), *area]))
    copia = [e for e in copia if e not in para]
    return {"para": para, "copia": copia, "reply_to": area}
