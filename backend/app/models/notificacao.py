"""
Destinatários institucionais das notificações.

Linha única (`id = 1`): o destinatário do departamento FISCAL e uma cópia
permanente (ex.: controladoria, que acompanha todos os processos). A cópia da
área responsável NÃO fica aqui — ela mora na própria `Area.emails_copia`,
porque é a área que é dona dos processos.

Antes esses e-mails viviam só no `.env` (`FISCAL_EMAILS`): mudavam raramente,
mas mudar exigia acesso ao servidor e reinício. O `.env` continua sendo o valor
inicial (ver `services/notificacao_config.py`).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfigNotificacao(Base):
    __tablename__ = "config_notificacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    # Listas separadas por vírgula (mesmo formato do .env que elas substituem).
    fiscal_emails: Mapped[str] = mapped_column(String(500), default="")
    copia_permanente: Mapped[str] = mapped_column(String(500), default="")
    atualizado_por: Mapped[str] = mapped_column(String(120), default="")
    atualizado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
