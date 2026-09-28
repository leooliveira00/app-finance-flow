"""
Entrypoint da aplicação FastAPI do FinanceFlow.

Responsabilidades deste arquivo:
- Criar a instância FastAPI.
- Aplicar configurações de CORS (para o frontend em :3000 conversar com :8000).
- Registrar os routers da aplicação.
- Disparar a descoberta automática de módulos de rateio na inicialização.

NÃO contém lógica de negócio. Toda a lógica vive nos módulos de rateio
(backend/app/modules/) e nos routers (backend/app/routers/).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401 — registra os modelos ORM no metadata da Base
from app.config import get_settings
from app.db.base import Base
from app.db.migracoes import aplicar_migracoes
from app.db.seed import seed_inicial
from app.db.session import SessionLocal, engine
from app.modules._plano_saude import validators as ps_validators
from app.modules.registry import registry
from app.routers import (
    auth,
    cadastro,
    centros_custo,
    empresas,
    execucoes,
    fornecedores,
    linhas_telefonicas,
    notificacoes,
    organizacao,
    rateio,
)
from app.routers import (
    processos as processos_router,
)
from app.services import organizacao_fiscal, processos
from app.version import __version__

logger = logging.getLogger(__name__)


def _configurar_logs() -> None:
    """
    Garante que os logs da aplicação apareçam na saída do uvicorn.

    O uvicorn instala handlers nos loggers "uvicorn*"; o logger raiz fica sem
    handler e em WARNING, então todo INFO nosso era descartado — inclusive a linha
    de auditoria de cada inclusão no ERP ("ERP[TESTE] POST <url>"), que é o rastro
    de onde o lançamento foi gravado. Handler próprio no logger "app", sem
    propagar, mantém isso visível sem ligar o INFO de bibliotecas terceiras.
    """
    app_logger = logging.getLogger("app")
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:    %(name)s - %(message)s"))
        app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False


def _logar_bases_protheus() -> None:
    """
    Deixa explícito na subida ONDE se lê e ONDE se escreve no ERP.

    É a primeira das três marcações do destino de escrita (as outras: auditoria
    por execução e prefixo [TESTE] no e-mail ao fiscal). A coerência URL x rótulo
    já foi validada em `Settings` — aqui só se torna visível.
    """
    settings = get_settings()
    # WARNING (não INFO): o uvicorn suprime INFO dos loggers da app, e esta linha
    # precisa aparecer sempre — é ela que responde "para onde estou escrevendo?".
    logger.warning(
        "Protheus | LEITURA: %s (verify_ssl=%s) | ESCRITA [%s]: %s (verify_ssl=%s) "
        "— TODA inclusão no ERP vai para a base de ESCRITA",
        settings.protheus_read_base_url or "(não configurada)",
        settings.protheus_read_verify_ssl,
        settings.protheus_write_ambiente.upper() or "(sem rótulo)",
        settings.protheus_write_base_url or "(não configurada)",
        settings.protheus_write_verify_ssl,
    )
    # Config incoerente é avisada alto, mas NÃO impede a subida: o que ela impede é
    # a inclusão no ERP (cobrada em services.protheus._post_erp).
    for problema in settings.problemas_escrita():
        logger.error("Protheus ESCRITA bloqueada: %s", problema)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Ciclo de vida da aplicação.

    Na subida (antes do `yield`):
    - registra no log as bases Protheus em uso (leitura x escrita);
    - cria o schema do banco (create_all) e roda o seed inicial (idempotente);
    - dispara a descoberta automática dos módulos de rateio (registry).

    Na descida (após o `yield`): ponto para liberar recursos, se houver.
    """
    _configurar_logs()
    # Versão do build que subiu: é o que amarra um comportamento observado em
    # produção ao commit/tag que o produziu (mesmo valor servido em /api/health).
    logger.warning("FinanceFlow | versao %s", __version__)
    _logar_bases_protheus()
    Base.metadata.create_all(bind=engine)
    aplicar_migracoes(engine)
    with SessionLocal() as db:
        seed_inicial(db)
        # Empresas/fornecedores do banco sobrepõem os literais dos validators
        # (detecção de empresa por CNPJ na reconciliação). Fonte única = cadastro.
        cfg_fiscal = organizacao_fiscal.carregar_config_fiscal(db)
        ps_validators.configurar(
            cfg_fiscal.empresas_por_nome,
            cfg_fiscal.empresas_por_cnpj,
            cfg_fiscal.cnpj_operadora,
        )

    registry.discover()
    # Um processo novo entra disponível; os desativados pelo admin permanecem
    # desativados. Depois da descoberta, porque a lista vem do registry.
    with SessionLocal() as db:
        processos.sincronizar(db, [m.tipo for m in registry.list_modules()])
    yield
    # TODO: cleanup de recursos na finalização, se necessário.


def create_app() -> FastAPI:
    """
    Application factory.

    Monta a instância FastAPI com metadados, CORS e routers.
    Mantida como função para facilitar testes e múltiplas instâncias.
    """
    settings = get_settings()

    app = FastAPI(
        title="FinanceFlow",
        description=(
            "Plataforma modular para lançamentos de rateio contábil "
            "integrada ao ERP Protheus."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    # CORS: libera o frontend (Vite/nginx) a consumir a API.
    # As origens permitidas são configuráveis via .env (ver config.py).
    # Métodos e headers se limitam ao que a API e o frontend (api.ts) usam; o
    # preflight OPTIONS é respondido pelo próprio middleware.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.lista_cors(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Registro dos routers da aplicação.
    # O prefixo /api é aplicado aqui para manter os routers agnósticos.
    app.include_router(auth.router, prefix="/api")
    app.include_router(cadastro.router, prefix="/api")
    app.include_router(centros_custo.router, prefix="/api")
    app.include_router(empresas.router, prefix="/api")
    app.include_router(execucoes.router, prefix="/api")
    app.include_router(linhas_telefonicas.router, prefix="/api")
    app.include_router(fornecedores.router, prefix="/api")
    app.include_router(notificacoes.router, prefix="/api")
    app.include_router(processos_router.router, prefix="/api")
    app.include_router(organizacao.router, prefix="/api")
    app.include_router(rateio.router, prefix="/api")

    return app


# Instância usada pelo uvicorn: `uvicorn app.main:app`. O nome sombreia o pacote
# `app` neste módulo, o que o mypy sinaliza; é a convenção do ASGI e mudar o nome
# quebraria o comando de subida.
app = create_app()  # type: ignore[assignment]
