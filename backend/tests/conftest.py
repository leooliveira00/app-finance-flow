"""
Configuração comum dos testes do backend.

Testes marcados com `@pytest.mark.integration` dependem de arquivos reais de
amostra, que não são versionados. Eles só rodam com `--run-integration`; sem a
flag, aparecem no relatório como pulados por esse motivo explícito. Com a flag,
dados ausentes são FALHA, não skip: quem pediu a integração quer saber que ela
não rodou.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="roda também os testes com dados reais de amostra (marker `integration`)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-integration"):
        return
    pular = pytest.mark.skip(reason="teste de integração: rode com --run-integration")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(pular)
