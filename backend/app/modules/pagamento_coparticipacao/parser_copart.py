"""
Parser do CONSOLIDADO de coparticipação (pagamento ao plano — Unimed).

Diferente da mensalidade (uma planilha por operadora), a coparticipação vem num
único consolidado com AS DUAS EMPRESAS (Vertex/Zenith), distinguidas pelo
`CNPJ` de cada linha. Uma linha por beneficiário (titular + dependentes), com o
valor já pronto em `VLR_PARTICIPACAO`.

Produz os MESMOS dataclasses da mensalidade (`LinhaValor`/`PlanilhaValores`) —
reaproveitando os helpers de normalização — para que `_plano_saude.calculator`
consuma o resultado sem qualquer alteração. Puro: não acessa banco nem rede.

Mapeamento consolidado -> LinhaValor:
- `valor`            <- VLR_PARTICIPACAO
- `competencia`      <- REFERENCIA (AAAAMM)
- `grupo_familiar`   <- CPF_TITULAR (chave de agregação da família)
- `is_titular`       <- GRAU_DEPENDENCIA == 0 | CPF_DEPENDENTE == CPF_TITULAR | NOME_DEPENDENCIA == "TITULAR"
- `empresa_planilha` <- CNPJ -> empresa (Vertex/Zenith), casa com a NF/boleto
"""

from __future__ import annotations

import re
from typing import Any

from app.modules._plano_saude import validators
from app.modules._plano_saude.parser import (
    EXTENSOES_PLANILHA,
    LinhaValor,
    PlanilhaValores,
    _abrir_worksheet,
    _cel,
    _mapa_colunas,
    _norm_cabecalho,
    _normalizar_competencia,
    _resolver_indices,
    _texto,
    _to_decimal,
    normalizar_cpf,
)

# A coparticipação é enviada pela Unimed (Bradesco fica para depois).
OPERADORA = "unimed"

# Nomes canônicos -> cabeçalho esperado no consolidado (comparado já normalizado).
_COLS_COPART = {
    "referencia": "REFERENCIA",
    "cnpj": "CNPJ",
    "num_contrato": "NUM_CONTRATO",
    "matricula": "MATRICULA_DO_BENEFICIARIO",
    "cpf_titular": "CPF_TITULAR",
    "nome_titular": "NOME_TITULAR",
    "cpf_dependente": "CPF_DEPENDENTE",
    "nome_dependente": "NOME_DEPENDENTE",
    "grau_dependencia": "GRAU_DEPENDENCIA",
    "nome_dependencia": "NOME_DEPENDENCIA",
    "valor": "VLR_PARTICIPACAO",
}
# Colunas que identificam o consolidado sem ambiguidade.
_ASSINATURA_COPART = ("cpf_titular", "valor", "cnpj")

def _empresa_do_cnpj(valor: Any) -> str | None:
    """Empresa pelo CNPJ, lendo o mapa ÚNICO dos validators AO VIVO (o cadastro do
    banco sobrepõe esse mapa no startup — ver validators.configurar)."""
    digitos = re.sub(r"\D", "", str(valor or ""))
    if not digitos:
        return None
    alvo = digitos.zfill(14)
    for cnpj, empresa in validators._EMPRESAS_POR_CNPJ.items():
        if re.sub(r"\D", "", cnpj).zfill(14) == alvo:
            return empresa
    return None


def _e_titular(grau: Any, cpf_dep: str | None, cpf_tit: str | None, nome_dep: Any) -> bool:
    """Titular quando grau 0, ou o CPF do dependente é o do titular, ou rótulo 'TITULAR'."""
    if _texto(grau) in ("0", "0.0"):
        return True
    if cpf_dep and cpf_tit and cpf_dep == cpf_tit:
        return True
    return _norm_cabecalho(nome_dep) == "TITULAR"


def detectar_consolidado(cabecalho: tuple[Any, ...]) -> bool:
    """True se o cabeçalho tem a assinatura do consolidado de coparticipação."""
    indices = _resolver_indices(_mapa_colunas(cabecalho), _COLS_COPART)
    return all(indices[c] is not None for c in _ASSINATURA_COPART)


def _ler_consolidado(ws, nome_arquivo: str) -> PlanilhaValores:
    linhas_iter = ws.iter_rows(values_only=True)
    cabecalho = next(linhas_iter, ())
    col = _resolver_indices(_mapa_colunas(cabecalho), _COLS_COPART)

    resultado = PlanilhaValores(
        operadora=OPERADORA, competencia=None, nome_arquivo=nome_arquivo
    )
    for linha in linhas_iter:
        valor = _to_decimal(_cel(linha, col["valor"]))
        cpf_titular = normalizar_cpf(_cel(linha, col["cpf_titular"]))
        # Sem valor ou sem titular -> linha irrelevante (cabeçalho residual/total).
        if valor is None or not cpf_titular:
            continue

        competencia = _normalizar_competencia(_cel(linha, col["referencia"]))
        if competencia and resultado.competencia is None:
            resultado.competencia = competencia

        cpf_dep = normalizar_cpf(_cel(linha, col["cpf_dependente"]))
        resultado.linhas.append(
            LinhaValor(
                operadora=OPERADORA,
                competencia=competencia or "",
                grupo_familiar=cpf_titular,
                is_titular=_e_titular(
                    _cel(linha, col["grau_dependencia"]),
                    cpf_dep,
                    cpf_titular,
                    _cel(linha, col["nome_dependencia"]),
                ),
                nome=_texto(_cel(linha, col["nome_dependente"])),
                nome_titular=_texto(_cel(linha, col["nome_titular"])) or None,
                cpf=cpf_dep,
                cpf_titular=cpf_titular,
                matricula=_texto(_cel(linha, col["matricula"])) or None,
                empresa_planilha=_empresa_do_cnpj(_cel(linha, col["cnpj"])),
                valor=valor,
            )
        )
    return resultado


# ---------------------------------------------------------------------------
# API pública (espelha _plano_saude.parser, consumida pelo module.py)
# ---------------------------------------------------------------------------
def _arquivos_planilha(arquivos: dict[str, bytes]) -> dict[str, bytes]:
    return {
        nome: conteudo
        for nome, conteudo in arquivos.items()
        if nome.lower().endswith(EXTENSOES_PLANILHA)
    }


def _consolidados(arquivos: dict[str, bytes]) -> dict[str, bytes]:
    """Só as planilhas cujo cabeçalho bate com a assinatura do consolidado."""
    achados: dict[str, bytes] = {}
    for nome, conteudo in _arquivos_planilha(arquivos).items():
        try:
            cabecalho = next(_abrir_worksheet(conteudo).iter_rows(values_only=True), ())
        except Exception:  # noqa: BLE001 — ilegível vira "não reconhecida"
            continue
        if detectar_consolidado(cabecalho):
            achados[nome] = conteudo
    return achados


def ler_consolidado(nome_arquivo: str, conteudo: bytes) -> PlanilhaValores:
    """Lê um consolidado a partir dos bytes (assinatura já validada)."""
    return _ler_consolidado(_abrir_worksheet(conteudo), nome_arquivo)


def validar_estrutura(arquivos: dict[str, bytes]) -> tuple[list[str], list[str]]:
    """(erros, alertas) — exige ao menos um consolidado reconhecível."""
    erros: list[str] = []
    alertas: list[str] = []
    if not _arquivos_planilha(arquivos):
        erros.append("Nenhuma planilha (.xlsx) foi enviada.")
        return erros, alertas
    if not _consolidados(arquivos):
        erros.append(
            "Nenhum consolidado de coparticipação reconhecido "
            "(faltam colunas CPF_TITULAR / VLR_PARTICIPACAO / CNPJ)."
        )
    return erros, alertas


def ler(
    arquivos: dict[str, bytes],
    dados_externos: dict[str, Any],
) -> list[PlanilhaValores]:
    """Lê todos os consolidados enviados (dados_externos entra só no calculator)."""
    return [
        ler_consolidado(nome, conteudo)
        for nome, conteudo in _consolidados(arquivos).items()
    ]
