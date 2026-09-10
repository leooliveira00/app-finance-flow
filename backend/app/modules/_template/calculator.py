"""
Lógica de cálculo do rateio (template).

Responsabilidade: a partir dos dados já normalizados pelo `parser`, aplicar
as regras de negócio do rateio e produzir a lista final de `ItemRateio`
(um item por colaborador).

Aqui mora toda a REGRA DE NEGÓCIO do rateio: critérios de distribuição,
proporções, arredondamentos e o ajuste de centavos. Este módulo não lê
arquivos nem conhece formato de entrada — recebe dados limpos do parser.

Cuidados ao implementar:
- Use Decimal em todos os cálculos monetários (nunca float).
- Defina e documente a política de arredondamento (ex.: ROUND_HALF_UP) e
  como tratar a sobra/diferença de centavos para que a soma dos itens bata
  exatamente com o valor total rateado.
"""

from typing import Any

# from decimal import Decimal, ROUND_HALF_UP
from app.modules.base import ItemRateio


def calcular(
    dados_normalizados: Any,
    dados_externos: dict[str, Any],
) -> list[ItemRateio]:
    """
    Aplica as regras do rateio e retorna um ItemRateio por colaborador.

    Passos sugeridos:
    1. Determinar a base de rateio (valor total e critério de distribuição).
    2. Calcular o valor de cada colaborador, mantendo Decimal.
    3. Resolver a diferença de centavos (a soma dos itens deve igualar o
       total).
    4. Montar e retornar a lista de ItemRateio preenchendo todos os campos
       (cpf, nome, departamento, centro_de_custo, valor, historico).

    Args:
        dados_normalizados: estrutura produzida por `parser.ler`.
        dados_externos: dados de apoio (ex.: centros de custo do Protheus).

    Returns:
        list[ItemRateio] — resultado final do rateio.
    """
    # TODO: implementar a regra de negócio do rateio e construir os ItemRateio.
    raise NotImplementedError
