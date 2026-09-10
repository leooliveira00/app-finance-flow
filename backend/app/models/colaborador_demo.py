"""
Cadastro FICTÍCIO de colaboradores, usado só para demonstração offline.

Em produção, colaboradores SEMPRE vêm do Protheus em tempo real
(`services/protheus.listar_colaboradores`) — nunca duplicados no Postgres, para
não haver duas fontes de verdade divergentes. Esta tabela existe apenas porque
a versão pública não tem um ERP real para consultar: o router
(`routers/rateio.py`) usa este cadastro no lugar da chamada ao Protheus SOMENTE
quando `PROTHEUS_READ_BASE_URL` está vazia — ou seja, apenas quando o ERP nunca
foi configurado. Uma falha de rede com o ERP JÁ configurado continua sendo erro
(502), nunca cai para este cadastro — misturar dado fictício com uma
indisponibilidade real do ERP mascararia o problema.

Mesmo formato de dict que o cliente Protheus devolve (ver
`services/cadastro.carregar_colaboradores_demo`), consumido pelos calculators
de coparticipação e de mensalidade (`_plano_saude/calculator.py`).
"""

from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ColaboradorDemo(Base):
    __tablename__ = "colaborador_demo"

    id: Mapped[int] = mapped_column(primary_key=True)
    cpf: Mapped[str] = mapped_column(String(11), unique=True)
    nome: Mapped[str] = mapped_column(String(120), default="")
    salario: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    matricula: Mapped[str] = mapped_column(String(20), default="")
    filial: Mapped[str] = mapped_column(String(10), default="")
    empresa: Mapped[str] = mapped_column(String(120), default="")
    # "ATIVO" | "DEMITIDO" (mesmo vocabulário do Protheus real — ver
    # `calculator.SITUACOES_INATIVAS`).
    situacao: Mapped[str] = mapped_column(String(20), default="ATIVO")
    centro_custo: Mapped[str] = mapped_column(String(60), default="")
    classe_valor: Mapped[str] = mapped_column(String(60), default="")
