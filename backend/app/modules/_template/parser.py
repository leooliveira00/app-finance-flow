"""
Leitura e normalização dos arquivos de entrada (template).

Responsabilidade: transformar os bytes crus dos uploads (planilhas das
operadoras, relatórios, etc.) em estruturas de dados Python limpas e
validadas, prontas para o `calculator`.

Aqui mora todo o conhecimento sobre o FORMATO dos arquivos de entrada:
quais colunas existem, seus nomes, tipos e como normalizá-los. O `calculator`
não deve conhecer formato de arquivo — só recebe dados já normalizados.

Ferramentas previstas na stack: pandas + openpyxl para ler .xlsx/.csv.
"""

from typing import Any

# from io import BytesIO
# import pandas as pd  # leitura de planilhas (.xlsx via openpyxl, .csv)

# Colunas obrigatórias esperadas no(s) arquivo(s) de entrada.
# TODO: ajustar para as colunas reais do rateio (ex.: CPF, valor, etc.).
COLUNAS_OBRIGATORIAS: list[str] = []


def validar_estrutura(
    arquivos: dict[str, bytes],
) -> tuple[list[str], list[str]]:
    """
    Verifica a estrutura dos arquivos sem executar o cálculo.

    Deve checar: presença dos arquivos esperados, existência das colunas
    em COLUNAS_OBRIGATORIAS e tipos básicos. Não interrompe no primeiro
    problema — acumula tudo para o usuário corrigir de uma vez.

    Args:
        arquivos: mapa nome_do_arquivo -> conteúdo em bytes.

    Returns:
        (erros, alertas): erros bloqueantes e alertas não bloqueantes.
        Usado por `module.validar_inputs` para montar o ValidationResult.
    """
    # TODO: abrir cada arquivo (ex.: pd.read_excel(BytesIO(bytes))),
    #       conferir COLUNAS_OBRIGATORIAS e acumular erros/alertas.
    raise NotImplementedError


def ler(
    arquivos: dict[str, bytes],
    dados_externos: dict[str, Any],
) -> Any:
    """
    Lê e normaliza os arquivos de entrada para uso pelo calculator.

    Deve produzir uma estrutura estável e tipada (ex.: um DataFrame ou uma
    lista de dataclasses) com os dados já limpos: CPFs sem máscara, valores
    convertidos para Decimal, colunas renomeadas para nomes canônicos.

    Args:
        arquivos: mapa nome_do_arquivo -> conteúdo em bytes.
        dados_externos: dados de apoio (ex.: cadastro do Protheus) que possam
                        ser necessários já na normalização (ex.: enriquecer
                        com centro de custo).

    Returns:
        Dados normalizados no formato que o `calculator.calcular` espera.
        Defina e documente esse formato ao implementar o rateio real.
    """
    # TODO: ler os arquivos com pandas, normalizar e retornar a estrutura
    #       que o calculator consumirá.
    raise NotImplementedError
