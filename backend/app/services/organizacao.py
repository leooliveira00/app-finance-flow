"""
Organização: usuários, áreas (setores) e o mapa área↔rateios — no Postgres.

Substitui o seed em memória (`app.auth.seed`) como FONTE de verdade em runtime:
- Autenticação lê os usuários do banco (senha em hash bcrypt).
- A autorização por área resolve o mapa `área -> tipos de rateio` do banco.

O seed continua existindo apenas para a carga inicial (`app.db.seed`). A partir
daqui, as telas de cadastro (Configurações ▸ Organização) editam o banco.
"""

from __future__ import annotations

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.auth import (
    NIVEIS,
    NIVEL_OPERADOR,
    Area,
    AreaRateio,
    Usuario,
    UsuarioArea,
)


def _hash(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


def _normalizar_nivel(nivel: str | None) -> str:
    """Garante um nível válido (default operador)."""
    return nivel if nivel in NIVEIS else NIVEL_OPERADOR


def _areas_do_usuario(usuario: Usuario) -> list[str]:
    """Áreas do usuário como lista de nomes; admin é representado por ["*"]."""
    if usuario.admin:
        return ["*"]
    return [link.area.nome for link in usuario.area_links]


def _niveis_do_usuario(usuario: Usuario) -> dict[str, str]:
    """Mapa {nome_area: nivel} do usuário. Vazio para admin global."""
    if usuario.admin:
        return {}
    return {link.area.nome: link.nivel for link in usuario.area_links}


# ---------------------------------------------------------------------------
# Autenticação / autorização (fonte: banco)
# ---------------------------------------------------------------------------
def autenticar(db: Session, email: str, senha: str) -> dict | None:
    """Valida e-mail/senha (bcrypt). Retorna {email, nome, areas, niveis} ou None."""
    usuario = db.scalar(
        select(Usuario)
        .options(selectinload(Usuario.area_links).selectinload(UsuarioArea.area))
        .where(Usuario.email == email.strip().lower(), Usuario.ativo.is_(True))
    )
    if not usuario:
        return None
    if not bcrypt.checkpw(senha.encode(), usuario.senha_hash.encode()):
        return None
    return {
        "email": usuario.email,
        "nome": usuario.nome,
        "areas": _areas_do_usuario(usuario),
        "niveis": _niveis_do_usuario(usuario),
    }


def mapa_areas_rateios(db: Session) -> dict[str, list[str]]:
    """Mapa {nome_da_área: [tipos de rateio]} lido do banco (autorização)."""
    areas = db.scalars(select(Area).options(selectinload(Area.rateios))).all()
    return {a.nome: [r.tipo for r in a.rateios] for a in areas}


# ---------------------------------------------------------------------------
# CRUD de usuários
# ---------------------------------------------------------------------------
def _usuario_dict(u: Usuario) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "nome": u.nome,
        "admin": u.admin,
        "ativo": u.ativo,
        # Áreas com o nível do usuário em cada uma: [{area, nivel}, ...].
        "areas": [
            {"area": link.area.nome, "nivel": link.nivel} for link in u.area_links
        ],
    }


def listar_usuarios(db: Session) -> list[dict]:
    usuarios = db.scalars(
        select(Usuario)
        .options(selectinload(Usuario.area_links).selectinload(UsuarioArea.area))
        .order_by(Usuario.nome)
    ).all()
    return [_usuario_dict(u) for u in usuarios]


def _montar_links(db: Session, areas: list[dict]) -> list[UsuarioArea]:
    """
    Cria os vínculos usuário↔área (com nível) a partir de [{area, nivel}, ...].
    Áreas inexistentes são ignoradas.
    """
    if not areas:
        return []
    nomes = [a.get("area") for a in areas if a.get("area")]
    encontradas = {
        area.nome: area for area in db.scalars(select(Area).where(Area.nome.in_(nomes))).all()
    }
    links: list[UsuarioArea] = []
    for item in areas:
        area = encontradas.get(str(item.get("area") or ""))
        if area is not None:
            links.append(UsuarioArea(area=area, nivel=_normalizar_nivel(item.get("nivel"))))
    return links


def criar_usuario(
    db: Session, email: str, nome: str, senha: str, admin: bool, areas: list[dict]
) -> dict:
    usuario = Usuario(
        email=email.strip().lower(),
        nome=nome,
        senha_hash=_hash(senha),
        admin=admin,
        ativo=True,
        area_links=[] if admin else _montar_links(db, areas),
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return _usuario_dict(usuario)


def atualizar_usuario(
    db: Session,
    usuario_id: int,
    nome: str,
    email: str,
    admin: bool,
    ativo: bool,
    areas: list[dict],
    senha: str | None,
) -> dict | None:
    usuario = db.scalar(
        select(Usuario)
        .options(selectinload(Usuario.area_links).selectinload(UsuarioArea.area))
        .where(Usuario.id == usuario_id)
    )
    if usuario is None:
        return None
    usuario.nome = nome
    usuario.email = email.strip().lower()
    usuario.admin = admin
    usuario.ativo = ativo
    # Remove os vínculos antigos e dá flush ANTES de reinserir: senão o SQLAlchemy
    # insere primeiro e colide com a PK (usuario_id, area_id) de usuario_area.
    usuario.area_links.clear()
    db.flush()
    if not admin:
        usuario.area_links = _montar_links(db, areas)
    if senha:
        usuario.senha_hash = _hash(senha)
    db.commit()
    db.refresh(usuario)
    return _usuario_dict(usuario)


def remover_usuario(db: Session, usuario_id: int) -> bool:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        return False
    db.delete(usuario)
    db.commit()
    return True


class SenhaAtualInvalida(Exception):
    """A senha atual informada não confere (autogestão de perfil)."""


def atualizar_perfil(
    db: Session, email: str, nome: str | None, senha_atual: str | None, senha_nova: str | None
) -> dict | None:
    """
    Autogestão do PRÓPRIO usuário: altera nome e/ou senha. NÃO altera o e-mail.
    Trocar a senha exige a senha atual correta (lança SenhaAtualInvalida).
    """
    usuario = db.scalar(
        select(Usuario)
        .options(selectinload(Usuario.area_links).selectinload(UsuarioArea.area))
        .where(Usuario.email == email)
    )
    if usuario is None:
        return None
    if nome:
        usuario.nome = nome
    if senha_nova:
        if not senha_atual or not bcrypt.checkpw(senha_atual.encode(), usuario.senha_hash.encode()):
            raise SenhaAtualInvalida()
        usuario.senha_hash = _hash(senha_nova)
    db.commit()
    db.refresh(usuario)
    return {
        "email": usuario.email,
        "nome": usuario.nome,
        "areas": _areas_do_usuario(usuario),
        "niveis": _niveis_do_usuario(usuario),
    }


# ---------------------------------------------------------------------------
# CRUD de áreas (setores)
# ---------------------------------------------------------------------------
def _area_dict(a: Area) -> dict:
    return {
        "id": a.id,
        "nome": a.nome,
        "rateios": [r.tipo for r in a.rateios],
        "emails_copia": a.emails_copia or "",
        "num_usuarios": len(a.usuario_links),
    }


def listar_areas(db: Session) -> list[dict]:
    areas = db.scalars(
        select(Area)
        .options(selectinload(Area.rateios), selectinload(Area.usuario_links))
        .order_by(Area.nome)
    ).all()
    return [_area_dict(a) for a in areas]


def criar_area(db: Session, nome: str, rateios: list[str], emails_copia: str = "") -> dict:
    area = Area(
        nome=nome,
        emails_copia=emails_copia,
        rateios=[AreaRateio(tipo=t) for t in rateios],
    )
    db.add(area)
    db.commit()
    db.refresh(area)
    return _area_dict(area)


def atualizar_area(
    db: Session, area_id: int, nome: str, rateios: list[str], emails_copia: str | None = None
) -> dict | None:
    area = db.scalar(
        select(Area)
        .options(selectinload(Area.rateios), selectinload(Area.usuario_links))
        .where(Area.id == area_id)
    )
    if area is None:
        return None
    area.nome = nome
    if emails_copia is not None:
        area.emails_copia = emails_copia
    # Remove os vínculos antigos e dá flush ANTES de inserir os novos: senão o
    # SQLAlchemy insere primeiro e colide com a unique (area_id, tipo) = uq_area_tipo.
    area.rateios.clear()
    db.flush()
    area.rateios = [AreaRateio(tipo=t) for t in rateios]
    db.commit()
    db.refresh(area)
    return _area_dict(area)


def remover_area(db: Session, area_id: int) -> bool:
    area = db.get(Area, area_id)
    if area is None:
        return False
    db.delete(area)
    db.commit()
    return True
