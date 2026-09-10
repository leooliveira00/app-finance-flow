"""
Modelos ORM da plataforma.

Importa todos os modelos para que fiquem registrados no metadata da Base
(usado por `Base.metadata.create_all` no startup).
"""

from app.models.auth import Area, AreaRateio, Usuario, UsuarioArea
from app.models.colaborador_demo import ColaboradorDemo
from app.models.coparticipacao import (
    ColaboradorPJ,
    FaixaCoparticipacao,
    ParametroRateio,
    ValorCoparticipacao,
)
from app.models.execucao import Documento, EnvioErp, EnvioTentativa, Execucao
from app.models.notificacao import ConfigNotificacao
from app.models.organizacao_fiscal import Empresa, Fornecedor
from app.models.pagamento import CentroCusto
from app.models.processo import ProcessoStatus
from app.models.telefonia import LinhaTelefonica

__all__ = [
    "Area",
    "AreaRateio",
    "Usuario",
    "UsuarioArea",
    "FaixaCoparticipacao",
    "ValorCoparticipacao",
    "ParametroRateio",
    "ColaboradorPJ",
    "ColaboradorDemo",
    "CentroCusto",
    "Empresa",
    "Fornecedor",
    "ConfigNotificacao",
    "ProcessoStatus",
    "LinhaTelefonica",
    "Execucao",
    "Documento",
    "EnvioErp",
    "EnvioTentativa",
]
