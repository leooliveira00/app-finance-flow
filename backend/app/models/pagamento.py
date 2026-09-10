"""
Cadastro de apoio do rateio de PAGAMENTO.

- CentroCusto: dicionário CÓDIGO -> NOME amigável do centro de custo. Não é
  fonte de dados contábeis (o centro de custo do colaborador comum vem da API);
  serve apenas para EXIBIR o nome no lugar do código na tela de resultado e para
  alimentar o seletor ao atribuir um PJ a um centro de custo.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CentroCusto(Base):
    __tablename__ = "centro_custo"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(60), unique=True)
    nome: Mapped[str] = mapped_column(String(160), default="")
    empresa: Mapped[str] = mapped_column(String(120), default="")
