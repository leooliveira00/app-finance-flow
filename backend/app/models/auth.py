"""
Modelos de autenticação e segregação por área.

- Usuario: credenciais (senha em hash bcrypt) + flag admin (vê todos os rateios).
- Area: agrupa rateios (por `tipo`) visíveis; usuários pertencem a áreas.
- UsuarioArea: associação usuário↔área com o NÍVEL do usuário naquela área
  (`operador` ou `admin_area`). É um association-object (não um `Table` puro)
  justamente para carregar a coluna `nivel` por par (usuario, área).
- AreaRateio: tipos de rateio de cada área (o antigo mapa AREAS_RATEIOS).

Níveis por área:
- `operador`: processa os rateios da área e envia ao ERP; NÃO vê dados de
  auditoria (salário/teto — redigidos no backend).
- `admin_area`: tudo do operador + auditoria (salário/teto) + edita o cadastro
  dos rateios da sua área.
O admin GLOBAL (`Usuario.admin`) continua acima disso e é representado por "*".
"""

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Níveis possíveis na associação usuário↔área.
NIVEL_OPERADOR = "operador"
NIVEL_ADMIN_AREA = "admin_area"
NIVEIS = (NIVEL_OPERADOR, NIVEL_ADMIN_AREA)


class UsuarioArea(Base):
    """Vínculo usuário↔área com o nível de acesso do usuário naquela área."""

    __tablename__ = "usuario_area"

    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True
    )
    area_id: Mapped[int] = mapped_column(
        ForeignKey("area.id", ondelete="CASCADE"), primary_key=True
    )
    nivel: Mapped[str] = mapped_column(String(20), default=NIVEL_OPERADOR)

    usuario: Mapped["Usuario"] = relationship(back_populates="area_links")
    area: Mapped["Area"] = relationship(back_populates="usuario_links")


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True)  # credencial de login
    nome: Mapped[str] = mapped_column(String(120))
    senha_hash: Mapped[str] = mapped_column(String(255))
    admin: Mapped[bool] = mapped_column(Boolean, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    area_links: Mapped[list["UsuarioArea"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )


class Area(Base):
    __tablename__ = "area"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(60), unique=True)
    # E-mails em CÓPIA nas notificações dos rateios desta área (separados por
    # vírgula). A área é dona dos processos, então a cópia mora nela: um rateio
    # novo herda os responsáveis sem cadastro adicional. Vazio = só o fiscal.
    emails_copia: Mapped[str] = mapped_column(String(500), default="")

    usuario_links: Mapped[list["UsuarioArea"]] = relationship(
        back_populates="area", cascade="all, delete-orphan"
    )
    rateios: Mapped[list["AreaRateio"]] = relationship(
        back_populates="area", cascade="all, delete-orphan"
    )


class AreaRateio(Base):
    __tablename__ = "area_rateio"
    __table_args__ = (UniqueConstraint("area_id", "tipo", name="uq_area_tipo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("area.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(80))  # tipo do rateio (ex.: pagamento-unimed)

    area: Mapped["Area"] = relationship(back_populates="rateios")
