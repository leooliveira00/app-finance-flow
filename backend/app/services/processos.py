"""
Disponibilidade dos processos: quem está ativo e quem não aceita novas execuções.

Regra única de "processo inativo", consumida pelo painel (`GET /modulos`), pelo
processamento (`POST /rateio/{tipo}/processar`) e pela tela de administração.
Inativo bloqueia INICIAR; não bloqueia consultar o histórico nem concluir uma
execução já gravada (ver `models/processo.py`).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.processo import ProcessoStatus


def sincronizar(db: Session, tipos: list[str]) -> None:
    """
    Garante uma linha por processo descoberto, ativa por padrão.

    Roda no startup, depois da descoberta dos módulos: um rateio novo entra
    disponível, sem precisar de cadastro manual. Linhas de processos que
    deixaram de existir são preservadas — se o pacote voltar, o estado dele
    volta com ele.
    """
    existentes = set(db.scalars(select(ProcessoStatus.tipo)).all())
    novos = [t for t in tipos if t not in existentes]
    if not novos:
        return
    db.add_all(ProcessoStatus(tipo=t, ativo=True) for t in novos)
    db.commit()


def tipos_inativos(db: Session) -> set[str]:
    """Tipos que não aceitam novas execuções."""
    return set(
        db.scalars(select(ProcessoStatus.tipo).where(ProcessoStatus.ativo.is_(False))).all()
    )


def esta_ativo(db: Session, tipo: str) -> bool:
    """Sem linha = ativo (processo recém-descoberto, antes do primeiro sync)."""
    linha = db.get(ProcessoStatus, tipo)
    return True if linha is None else linha.ativo


def listar(db: Session) -> dict[str, ProcessoStatus]:
    """Status por tipo, para a tela de administração."""
    return {p.tipo: p for p in db.scalars(select(ProcessoStatus)).all()}


def definir_ativo(db: Session, tipo: str, ativo: bool, usuario: str) -> ProcessoStatus:
    """Liga/desliga um processo, registrando quem fez."""
    linha = db.get(ProcessoStatus, tipo)
    if linha is None:
        linha = ProcessoStatus(tipo=tipo)
        db.add(linha)
    linha.ativo = ativo
    linha.atualizado_por = usuario
    db.commit()
    db.refresh(linha)
    return linha
