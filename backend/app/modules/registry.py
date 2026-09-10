"""
Registry de módulos de rateio com descoberta automática.

Objetivo: adicionar um novo rateio = copiar `_template/` para um novo pacote
e implementar. Nenhuma alteração é necessária aqui nem em qualquer outro
ponto da plataforma.

Como funciona:
- `discover()` varre o diretório `app/modules/`, importa cada subpacote e
  procura por classes que herdam de `RateioModule`.
- Cada classe encontrada é instanciada e registrada sob sua chave `tipo`.
- Pacotes cujo nome começa com `_` (ex.: `_template`) são IGNORADOS — são
  moldes/utilitários, não rateios ativos.

Uso:
    from app.modules.registry import registry
    registry.discover()                 # chamado no startup (lifespan)
    modulo = registry.get("plano-saude")
    todos = registry.list_modules()
"""

import importlib
import inspect
import logging
import pkgutil
from pathlib import Path

from app.modules.base import RateioModule

logger = logging.getLogger(__name__)


class ModuleRegistry:
    """
    Container dos módulos de rateio descobertos, indexados por `tipo`.

    Mantém uma instância única de cada `RateioModule` encontrado. Os módulos
    são considerados stateless quanto à descoberta — estado por execução não
    deve ser guardado na instância do módulo.
    """

    def __init__(self) -> None:
        # Mapa tipo -> instância do módulo de rateio.
        self._modules: dict[str, RateioModule] = {}

    def discover(self) -> None:
        """
        Varre `app/modules/`, importa cada subpacote e registra os módulos.

        Algoritmo previsto:
        1. Listar os subpacotes de `app.modules` (via pkgutil sobre este
           diretório), ignorando os que começam com `_`.
        2. Para cada subpacote, importar o módulo `module.py` (ou o próprio
           pacote) e inspecionar seus membros.
        3. Selecionar classes que herdam de `RateioModule` (exceto a própria
           base abstrata), instanciá-las e chamar `register()`.

        Idempotente: chamar mais de uma vez deve resultar no mesmo estado.
        """
        # Idempotente: recomeça do zero a cada chamada.
        self._modules.clear()

        # Diretório físico deste pacote (app/modules).
        package_dir = Path(__file__).resolve().parent

        for mod_info in pkgutil.iter_modules([str(package_dir)]):
            nome = mod_info.name

            # Ignora moldes/privados (_template) e arquivos não-pacote.
            if nome.startswith("_"):
                continue
            if not mod_info.ispkg:
                continue

            # Importa o módulo isoladamente: um módulo quebrado não pode
            # derrubar a descoberta dos demais.
            try:
                submodule = importlib.import_module(f"app.modules.{nome}.module")
            except Exception as exc:  # noqa: BLE001 — isola falha de import
                logger.warning("Módulo '%s' ignorado (falha ao importar): %s", nome, exc)
                continue

            for _, classe in inspect.getmembers(submodule, inspect.isclass):
                # Só classes concretas definidas NESTE submódulo (evita a base
                # abstrata e classes apenas importadas).
                if not issubclass(classe, RateioModule) or classe is RateioModule:
                    continue
                if classe.__module__ != submodule.__name__:
                    continue
                try:
                    self.register(classe())
                    logger.info("Rateio registrado: %s", classe().tipo)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Módulo '%s' não registrado: %s", nome, exc)

    def register(self, modulo: RateioModule) -> None:
        """
        Registra uma instância de módulo sob sua chave `tipo`.

        Valida que `tipo` está definido e que não há colisão com um módulo já
        registrado (dois rateios não podem compartilhar o mesmo `tipo`).
        """
        tipo = getattr(modulo, "tipo", None)
        if not tipo:
            raise ValueError(f"{type(modulo).__name__} não define `tipo`.")
        if tipo in self._modules:
            raise ValueError(f"Tipo de rateio duplicado: '{tipo}'.")
        self._modules[tipo] = modulo

    def get(self, tipo: str) -> RateioModule:
        """
        Retorna o módulo registrado para o `tipo` informado.

        Levanta KeyError quando o tipo não existe (o router converte em 404).
        """
        try:
            return self._modules[tipo]
        except KeyError:
            raise KeyError(f"Rateio '{tipo}' não encontrado.") from None

    def list_modules(self) -> list[RateioModule]:
        """Retorna todos os módulos registrados (para GET /api/modulos)."""
        return list(self._modules.values())


# Instância global compartilhada pela aplicação.
# Importada pelo main.py (discover no startup) e pelo router de rateio.
registry = ModuleRegistry()
