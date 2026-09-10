"""
Disponibilidade dos processos (rateios) na ferramenta.

Um processo INATIVO não aceita novas execuções e sai do painel. Ele NÃO some da
ferramenta: o histórico das execuções antigas continua consultável (são
lançamentos que existiram no ERP) e os cadastros dele seguem acessíveis ao
admin, porque é ali que se termina o que falta.

O registro existe para todos os processos descobertos no startup
(`services/processos.sincronizar`); ausência de linha equivale a ativo.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProcessoStatus(Base):
    __tablename__ = "processo_status"

    # O `tipo` do módulo de rateio (ex.: "pagamento-bradesco") é a identidade:
    # é ele que atravessa painel, permissões, execuções e envios.
    tipo: Mapped[str] = mapped_column(String(80), primary_key=True)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Quem desativou e quando: sem isso, um processo fora do painel em produção
    # vira mistério ("alguém desligou, não se sabe quando nem por quê").
    atualizado_por: Mapped[str] = mapped_column(String(120), default="")
    atualizado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
