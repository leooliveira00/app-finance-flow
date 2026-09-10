"""
Definição do módulo de rateio (template).

Este arquivo amarra as três peças de um rateio:
- a interface `RateioModule` (contrato),
- o `parser` (leitura dos arquivos de entrada),
- o `calculator` (lógica de cálculo).

Ao criar um rateio real a partir deste template:
1. Renomeie a classe (ex.: `PlanoSaudeRateio`).
2. Defina `tipo` (chave única usada na URL, ex.: "plano-saude") e `descricao`.
3. Implemente `validar_inputs` e `processar` orquestrando parser + calculator.

NÃO coloque lógica de leitura nem de cálculo aqui — delegue para
`parser.py` e `calculator.py`. Este arquivo é apenas a orquestração.
"""

from typing import Any

from app.modules.base import ItemRateio, RateioModule, ValidationResult

# Parte do molde: quem copia este template implementa `validar_inputs` e
# `processar` orquestrando os dois módulos. Sem uso até então, por isso o noqa.
from . import calculator, parser  # noqa: F401


class TemplateRateio(RateioModule):
    """
    Módulo de rateio de exemplo (template).

    Renomeie esta classe ao criar um rateio real. O registry detecta
    qualquer subclasse de `RateioModule` automaticamente.
    """

    # Identificador único do rateio, usado na rota /api/rateio/{tipo}/...
    # TODO: trocar por um slug estável e único (ex.: "plano-saude").
    tipo: str = "template"

    # Rótulo CURTO para UI (chips, badges, títulos) — ex.: "Plano de Saúde".
    # TODO: usar um nome curto e amigável (2-3 palavras).
    nome: str = "Template"

    # Descrição legível e completa (tooltip / listagem detalhada).
    # TODO: descrever o rateio (ex.: "Rateio do plano de saúde por colaborador").
    descricao: str = "Template — copie e implemente um rateio real."

    def validar_inputs(
        self,
        arquivos: dict[str, bytes],
        dados_externos: dict[str, Any],
    ) -> ValidationResult:
        """
        Valida os arquivos e dados de entrada antes do processamento.

        Orquestração sugerida:
        1. Conferir se os arquivos esperados estão presentes em `arquivos`.
        2. Delegar a `parser` a checagem de estrutura/colunas obrigatórias.
        3. Acumular erros bloqueantes e alertas não bloqueantes.
        4. Retornar ValidationResult(valido=not erros, erros, alertas).
        """
        # TODO: implementar a validação real usando parser.py.
        #   Ex.: parser.validar_estrutura(arquivos) -> (erros, alertas)
        raise NotImplementedError

    def processar(
        self,
        arquivos: dict[str, bytes],
        dados_externos: dict[str, Any],
    ) -> list[ItemRateio]:
        """
        Executa o rateio e retorna um ItemRateio por colaborador.

        Orquestração sugerida:
        1. parser.ler(arquivos, dados_externos) -> dados normalizados.
        2. calculator.calcular(dados_normalizados, dados_externos)
           -> list[ItemRateio].
        3. Retornar a lista resultante.

        Deve ser chamado apenas após `validar_inputs` indicar valido=True.
        """
        # TODO: implementar orquestrando parser.ler(...) + calculator.calcular(...).
        #   dados = parser.ler(arquivos, dados_externos)
        #   return calculator.calcular(dados, dados_externos)
        raise NotImplementedError
