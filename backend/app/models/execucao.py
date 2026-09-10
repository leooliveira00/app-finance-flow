"""
Persistência das execuções de rateio confirmadas.

- Execucao: uma confirmação de rateio (snapshot do resultado em JSON + totais +
  status de envio ao ERP).
- Documento: os arquivos envolvidos (planilhas + NF/boleto), guardados como bytes
  no próprio banco (integridade transacional; download via API autenticada).
- EnvioErp: ESTADO ATUAL do envio ao ERP POR EMPRESA/NF (uma AE -> um título).
  Guarda o título retornado ou a mensagem de erro (upsert por empresa), base da
  idempotência do reenvio.
- EnvioTentativa: LOG imutável (append-only) de CADA tentativa de envio por
  empresa — para o usuário ver o histórico de tentativas e erros. Nunca é
  sobrescrito; o EnvioErp reflete a última tentativa de cada empresa.

status de Execucao: pendente_envio | parcial | enviado | erro_envio.
status de EnvioErp/EnvioTentativa: enviando | enviado | parcial | erro | pendente |
pulado. "enviando" é gravado ANTES do POST de um título e substituído pela
resposta; se sobrar, o envio caiu entre o POST e a resposta e não se sabe se o
título entrou (ver o tratamento em routers/execucoes.py).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Execucao(Base):
    __tablename__ = "execucao"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(80))
    competencia: Mapped[str] = mapped_column(String(20), default="")
    usuario: Mapped[str] = mapped_column(String(60), default="")
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(30), default="pendente_envio")
    # Quando a NF/boleto + nº dos títulos foram enviados ao dep. fiscal por e-mail.
    notificado_em: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # PARA QUEM foi ({para, copia}). Os destinatários vêm de cadastro que muda com
    # o tempo; sem registrar os do momento, "quem recebeu o e-mail do processo
    # 041?" fica sem resposta meses depois.
    notificado_para: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    resultado: Mapped[dict] = mapped_column(JSONB)  # snapshot (itens/agregado/divergências/...)

    documentos: Mapped[list[Documento]] = relationship(
        back_populates="execucao", cascade="all, delete-orphan"
    )
    envios: Mapped[list[EnvioErp]] = relationship(
        back_populates="execucao", cascade="all, delete-orphan"
    )
    tentativas: Mapped[list[EnvioTentativa]] = relationship(
        back_populates="execucao", cascade="all, delete-orphan"
    )


class Documento(Base):
    __tablename__ = "documento"

    id: Mapped[int] = mapped_column(primary_key=True)
    execucao_id: Mapped[int] = mapped_column(ForeignKey("execucao.id", ondelete="CASCADE"))
    categoria: Mapped[str] = mapped_column(String(20), default="")  # planilha | nf | boleto | outro
    nome: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(120), default="")
    conteudo: Mapped[bytes] = mapped_column(LargeBinary)

    execucao: Mapped[Execucao] = relationship(back_populates="documentos")


class EnvioErp(Base):
    __tablename__ = "envio_erp"

    id: Mapped[int] = mapped_column(primary_key=True)
    execucao_id: Mapped[int] = mapped_column(ForeignKey("execucao.id", ondelete="CASCADE"))
    empresa: Mapped[str] = mapped_column(String(120))
    # Unidade de envio DENTRO da empresa. Vazio no plano de saúde (um título por
    # empresa); na telefonia é a conta da Claro, porque cada boleto vira um título
    # e todos vão para a mesma empresa. É parte da chave do upsert e da trava de
    # reenvio: sem ela, o segundo boleto sobrescreveria o primeiro.
    referencia: Mapped[str] = mapped_column(String(60), default="")
    rest: Mapped[str] = mapped_column(String(20), default="")
    contrato: Mapped[str] = mapped_column(String(30), default="")
    titulo: Mapped[str] = mapped_column(String(30), default="")
    status: Mapped[str] = mapped_column(String(20), default="")  # enviando | enviado | parcial | erro
    mensagem: Mapped[str] = mapped_column(Text, default="")
    # Onde foi gravado: rótulo (teste | producao) e base de escrita usada. Sem
    # isto, depois do go-live não se distingue título real de título de teste.
    erp_ambiente: Mapped[str] = mapped_column(String(20), default="")
    erp_base_url: Mapped[str] = mapped_column(String(255), default="")
    # Envio em LOTE (desconto em folha): o ERP pode aceitar parte dos registros.
    # Guardamos o que foi enviado, o que ele aceitou e QUAIS matrículas ficaram
    # pendentes — é o que permite reenviar somente elas, sem duplicar as aceitas.
    enviados: Mapped[int] = mapped_column(Integer, default=0)
    aceitos: Mapped[int] = mapped_column(Integer, default=0)
    matriculas_pendentes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    atualizado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    execucao: Mapped[Execucao] = relationship(back_populates="envios")


class EnvioTentativa(Base):
    """
    Log imutável de uma tentativa de envio ao ERP (por empresa). Append-only:
    cada clique em "Enviar/Reenviar" gera uma linha por empresa processada,
    preservando o histórico de tentativas e erros (o EnvioErp guarda só o estado
    atual). `status`: enviado | erro | pendente | pulado (empresa já integrada).
    """

    __tablename__ = "envio_tentativa"

    id: Mapped[int] = mapped_column(primary_key=True)
    execucao_id: Mapped[int] = mapped_column(ForeignKey("execucao.id", ondelete="CASCADE"))
    empresa: Mapped[str] = mapped_column(String(120))
    referencia: Mapped[str] = mapped_column(String(60), default="")  # ver EnvioErp
    rest: Mapped[str] = mapped_column(String(20), default="")
    contrato: Mapped[str] = mapped_column(String(30), default="")
    titulo: Mapped[str] = mapped_column(String(30), default="")
    status: Mapped[str] = mapped_column(String(20), default="")
    mensagem: Mapped[str] = mapped_column(Text, default="")
    usuario: Mapped[str] = mapped_column(String(60), default="")  # quem disparou a tentativa
    # Destino desta tentativa (ver EnvioErp). Aqui é o registro que importa: é
    # imutável, então preserva o ambiente vigente em CADA tentativa.
    erp_ambiente: Mapped[str] = mapped_column(String(20), default="")
    erp_base_url: Mapped[str] = mapped_column(String(255), default="")
    # Resposta BRUTA do ERP ({http_status, body}). Guardada nas falhas: quando o
    # ERP aceita parte do lote (200 com totalOk menor), é a única fonte de quais
    # registros ele recusou — a mensagem interpretada não dá para reconstruir.
    resposta_erp: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    criado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    execucao: Mapped[Execucao] = relationship(back_populates="tentativas")
