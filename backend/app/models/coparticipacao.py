"""
Cadastro (parametrizável) da Coparticipação.

- FaixaCoparticipacao: faixa de SALÁRIO (salario_inicial..salario_final).
- ValorCoparticipacao: valor fixo por (faixa, tipo de exame).
- ParametroRateio: parâmetros gerais (ex.: teto_percentual_copart).

Estes modelos alimentam a tela de cadastro e são carregados pelo router para
compor `dados_externos["consenso"]` do módulo de coparticipação.
"""

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FaixaCoparticipacao(Base):
    __tablename__ = "faixa_coparticipacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(60))
    salario_inicial: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    salario_final: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    ordem: Mapped[int] = mapped_column(default=0)

    valores: Mapped[list["ValorCoparticipacao"]] = relationship(
        back_populates="faixa", cascade="all, delete-orphan"
    )


class ValorCoparticipacao(Base):
    __tablename__ = "valor_coparticipacao"
    __table_args__ = (UniqueConstraint("faixa_id", "tipo", name="uq_faixa_tipo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    faixa_id: Mapped[int] = mapped_column(ForeignKey("faixa_coparticipacao.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(20))  # consulta | simples | especial
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    faixa: Mapped["FaixaCoparticipacao"] = relationship(back_populates="valores")


class ParametroRateio(Base):
    """Parâmetros chave/valor (ex.: teto_percentual_copart='20', salario_padrao_pj='10000')."""

    __tablename__ = "parametro_rateio"

    chave: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor: Mapped[str] = mapped_column(String(255))
    descricao: Mapped[str] = mapped_column(String(255), default="")


class ColaboradorPJ(Base):
    """
    Colaborador PJ (cadastro especial). Não é buscado na API: usa o salário
    padrão de PJ (parâmetro salario_padrao_pj) para determinar a faixa.
    Chaveado por CPF (o mesmo do Consolidado).
    """

    __tablename__ = "colaborador_pj"

    id: Mapped[int] = mapped_column(primary_key=True)
    cpf: Mapped[str] = mapped_column(String(11), unique=True)
    nome: Mapped[str] = mapped_column(String(120), default="")
    # Alocação contábil para o rateio de PAGAMENTO (PJ não vem da API, então não
    # há dado fresco). Amarração EXCLUSIVA de PJ: o colaborador comum continua
    # vindo 100% da API a cada execução. Vazio = ainda não atribuído -> o
    # pagamento gera divergência para o operador escolher o centro de custo.
    # A coparticipação ignora estes campos.
    centro_custo: Mapped[str] = mapped_column(String(60), default="")
    empresa: Mapped[str] = mapped_column(String(120), default="")
    classe_valor: Mapped[str] = mapped_column(String(60), default="")
