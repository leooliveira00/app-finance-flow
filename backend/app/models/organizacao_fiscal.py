"""
Cadastro fiscal: Empresas do grupo e Fornecedores dos lançamentos.

Fonte ÚNICA (migrada de config.py + _plano_saude/validators.py) de:
- Empresa: rótulo, `rest` do Protheus, CNPJ próprio (tomador), rotina de
  lançamento no ERP ("ae"/"pre_nota") e constantes de pré-nota.
- Fornecedor: quem recebe o título no ERP — CNPJ (formatado no cadastro; só os
  dígitos no ERP). Vale para qualquer natureza: operadora de plano de saúde
  (Unimed, Bradesco) ou telefonia (Claro). Na reconciliação de NF/boleto do plano
  de saúde é ele que separa prestador de tomador.

Antes esses dados viviam espalhados em `config.py` (protheus_rests,
protheus_rotina_por_empresa, protheus_fornecedor_cnpj, prenota_*) e em
`validators.py` (_EMPRESAS_POR_NOME/_CNPJ, _CNPJ_UNIMED/_BRADESCO), inclusive o
mesmo CNPJ em dois formatos. Aqui ficam unificados e editáveis por tela.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Empresa(Base):
    __tablename__ = "empresa"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), unique=True)  # rótulo, ex.: "Vertex"
    rest: Mapped[str] = mapped_column(String(20), default="")    # ex.: "rest02"
    cnpj: Mapped[str] = mapped_column(String(20), default="")    # CNPJ próprio (tomador)
    # Rotina de lançamento no ERP: "ae" (padrão) ou "pre_nota".
    rotina_erp: Mapped[str] = mapped_column(String(20), default="ae")
    # Constantes usadas só na rotina de pré-nota (ex.: Zenith).
    prenota_produto: Mapped[str] = mapped_column(String(30), default="")
    prenota_filial: Mapped[str] = mapped_column(String(10), default="")


class Fornecedor(Base):
    """
    Fornecedor do título no ERP. Antes chamava-se `Operadora`, nome que descrevia
    só o caso do plano de saúde — a entidade é a mesma para a telefonia, e é o
    `fornecedor` que cada módulo de rateio declara.
    """

    __tablename__ = "fornecedor"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Chave de negócio, minúscula: é o `RateioModule.fornecedor` do módulo
    # ("unimed", "bradesco", "claro").
    nome: Mapped[str] = mapped_column(String(40), unique=True)
    # CNPJ do fornecedor (formatado). No ERP vai só os dígitos (derivado); na
    # reconciliação da NF/boleto separa prestador (fornecedor) de tomador (empresa).
    cnpj: Mapped[str] = mapped_column(String(20), default="")
