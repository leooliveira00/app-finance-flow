"""
Redação de dados de auditoria no resultado de um rateio.

Regra de negócio (níveis por área): o `operador` NÃO enxerga os dados de
auditoria — hoje o **salário** e o valor do **teto**, que vêm da API do Protheus
(não das planilhas). O `admin_area` (e o admin global) veem tudo.

A redação acontece na SAÍDA (serialização), nunca na persistência: o snapshot da
execução é gravado completo e redigido apenas na leitura, conforme o nível de
quem faz o request. Assim o admin_area consegue auditar depois, e a API nunca
entrega salário/teto a quem não tem direito (esconder no frontend não bastaria —
o dado apareceria na aba Network).
"""

from __future__ import annotations

from typing import Any

# Campos por colaborador que só admin_area/admin podem ver.
CAMPOS_AUDITORIA: frozenset[str] = frozenset({"salario", "teto"})


def _redigir_item(item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    return {chave: valor for chave, valor in item.items() if chave not in CAMPOS_AUDITORIA}


def redigir_resultado(resultado: Any, pode_auditar: bool) -> Any:
    """
    Devolve o resultado sem os campos de auditoria quando `pode_auditar` é False.
    Não muta o original (cria novos dicts) — importante porque o resultado pode
    ser o snapshot ORM da execução.
    """
    if pode_auditar or not isinstance(resultado, dict):
        return resultado
    itens = resultado.get("itens")
    if not isinstance(itens, list):
        return resultado
    return {**resultado, "itens": [_redigir_item(i) for i in itens]}
