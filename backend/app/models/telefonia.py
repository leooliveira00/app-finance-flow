"""
Cadastro de linhas telefônicas (telefonia móvel corporativa).

Uma linha do boleto da Claro não é rateada por cálculo: ela já vem com o valor
cobrado. O que a plataforma precisa saber é PARA ONDE esse valor vai — e é isso
que este cadastro guarda: número da linha -> centro de custo (+ colaborador
responsável, para controle interno).

Regra do domínio: 1 linha -> 1 centro de custo (sem rateio percentual). O
colaborador é informativo — o lançamento contábil segue o centro de custo,
inclusive para excedentes de uso.

Mantido pela área de TI (ver `routers/linhas_telefonicas.py`).
"""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LinhaTelefonica(Base):
    __tablename__ = "linha_telefonica"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Somente dígitos, com DDD (ex.: "11947703500") — é assim que o parser
    # normaliza o número lido do boleto, então o casamento é direto.
    numero: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    centro_custo: Mapped[str] = mapped_column(String(60))
    # Classe de valor contábil (C7_CLVL/D1_CLVL). Obrigatória como o centro de
    # custo — o ERP recusa o lançamento sem ela. O default vazio existe só para
    # registros anteriores a esta regra; o router não deixa mais gravar em branco
    # e a prévia bloqueia o lançamento até que sejam corrigidos.
    classe_valor: Mapped[str] = mapped_column(String(60), default="")
    # Conta Claro (nº da conta do boleto) à qual a linha está vinculada. Vazio =
    # não informado. Serve para conferir: se a linha for cobrada num boleto de
    # outra conta, ela migrou e o cadastro está defasado.
    conta: Mapped[str] = mapped_column(String(30), default="")
    # Responsável pela linha (controle interno; não afeta o lançamento).
    colaborador_cpf: Mapped[str] = mapped_column(String(11), default="")
    colaborador_nome: Mapped[str] = mapped_column(String(120), default="")
    # Linha desativada continua no cadastro (histórico), mas sinaliza ao usuário
    # quando volta a aparecer num boleto.
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    observacao: Mapped[str] = mapped_column(String(255), default="")
