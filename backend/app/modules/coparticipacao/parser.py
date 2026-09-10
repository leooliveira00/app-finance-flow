"""
Leitura e normalização do Consolidado de Coparticipação.

Responsabilidade (apenas FORMATO): transformar os bytes do Consolidado (planilha
enviada pela operadora) numa lista de eventos limpos (`EventoCoparticipacao`),
prontos para o `calculator`. Unimed e Bradesco usam o mesmo formato.

Colunas do Consolidado (nomes canônicos → cabeçalho tolerante):
    Nome Empresa (ignorado p/ cálculo), CPF Titular, Nome Titular,
    Nome Beneficiário, Data Atendimento, Procedimento, Valor Coparticipação,
    Nome Prestador Origem (ignorado).

Normalizações:
- CPF Titular → 11 dígitos (corrige zeros à esquerda).
- Data Atendimento → date (aceita datetime do openpyxl ou serial do Excel).
- Procedimento → tipo canônico (consulta | simples | especial) por palavra-chave
  (mapeamento 1:1). Não classificável → tipo None (o calculator sinaliza).
- Valor Coparticipação → Decimal (referência; NÃO é o valor descontado).

Há uma linha de TOTAL no fim do Consolidado (só o valor somado) → separada.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from openpyxl import load_workbook

EXTENSOES_PLANILHA: tuple[str, ...] = (".xlsx", ".xls")

# Epoch do serial de datas do Excel (sistema 1900; openpyxl usa 1899-12-30).
_EPOCH_EXCEL = datetime(1899, 12, 30)


# ---------------------------------------------------------------------------
# Estruturas de saída
# ---------------------------------------------------------------------------
@dataclass
class EventoCoparticipacao:
    """Um evento (linha do Consolidado): um procedimento de um beneficiário."""

    cpf_titular: str            # 11 dígitos
    nome_titular: str
    nome_beneficiario: str
    tipo: str | None            # "consulta" | "simples" | "especial" | None
    procedimento: str           # texto cru (para diagnóstico de não classificados)
    valor_coparticipacao: Decimal  # cobrança da operadora (referência)
    data_atendimento: date | None
    empresa: str | None = None  # Nome Empresa (informativo)
    operadora: str | None = None  # "unimed" | "bradesco" (layout detectado)


@dataclass
class Consolidado:
    """Resultado da leitura de um Consolidado de coparticipação."""

    nome_arquivo: str
    eventos: list[EventoCoparticipacao] = field(default_factory=list)
    total_informado: Decimal | None = None  # linha de total (conferência)


# ---------------------------------------------------------------------------
# Colunas / assinatura
# ---------------------------------------------------------------------------
# Layouts por operadora (Unimed e Bradesco usam cabeçalhos diferentes).
# Mesmas chaves canônicas em ambos; None = coluna inexistente naquele layout.
_COLS_UNIMED = {
    "nome_empresa": "Nome Empresa",
    "cpf_titular": "CPF Titular",
    "nome_titular": "Nome Titular",
    "nome_beneficiario": "Nome Beneficiário",
    "data_atendimento": "Data Atendimento",
    "procedimento": "Procedimento",
    "valor_coparticipacao": "Valor Coparticipação",
}
_COLS_BRADESCO = {
    "nome_empresa": None,
    "cpf_titular": "CPF DO TITULAR",
    "nome_titular": "NOME DO TITULAR",
    "nome_beneficiario": "NOME DO USUARIO",
    "data_atendimento": "DATA DE UTILIZACAO",
    "procedimento": "TIPO DE SERVICO",
    "valor_coparticipacao": "VALORDAPARTICIPACAO",
}
# Anotado porque os dois dicionários de colunas têm formas ligeiramente
# diferentes (um deles tem valores None), e sem o tipo o mypy infere `object`.
_LAYOUTS: Mapping[str, Mapping[str, str | None]] = {
    "unimed": _COLS_UNIMED,
    "bradesco": _COLS_BRADESCO,
}
# Colunas mínimas para reconhecer o Consolidado (em qualquer layout).
_OBRIGATORIAS = ("cpf_titular", "procedimento", "valor_coparticipacao")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sem_acento(texto: str) -> str:
    forma = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in forma if not unicodedata.combining(c))


def _norm_cabecalho(valor: Any) -> str:
    if valor is None:
        return ""
    texto = _sem_acento(str(valor)).upper()
    return re.sub(r"[^A-Z0-9]+", " ", texto).strip()


def normalizar_cpf(valor: Any) -> str | None:
    if valor is None:
        return None
    digitos = re.sub(r"\D", "", str(valor))
    if not digitos:
        return None
    return digitos.zfill(11) if len(digitos) <= 11 else digitos


def _to_decimal(valor: Any) -> Decimal | None:
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        return Decimal(str(valor)).quantize(Decimal("0.01"))
    texto = str(valor).strip()
    if not texto:
        return None
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def _to_date(valor: Any) -> date | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, (int, float)):
        try:
            return (_EPOCH_EXCEL + timedelta(days=int(valor))).date()
        except (ValueError, OverflowError):
            return None
    # string dd/mm/aaaa ou dd.mm.aaaa
    texto = str(valor).strip()
    for sep in ("/", ".", "-"):
        partes = texto.split(sep)
        if len(partes) == 3:
            try:
                d, m, a = (int(p) for p in partes)
                if a < 100:
                    a += 2000
                return date(a, m, d)
            except ValueError:
                pass
    return None


def _classificar_tipo(procedimento: str) -> str | None:
    """
    Mapeia o texto do Procedimento/Tipo de Serviço para o tipo canônico.

    Precedência importa: TERAPIA é enquadrada como CONSULTA (ex.: "TERAPIA
    SIMPLES" -> consulta, não simples). Só depois valem especial/simples.
    """
    alvo = _sem_acento(procedimento or "").upper()
    # Terapia: SÓ "TERAPIA SIMPLES" é mapeada (-> consulta). Qualquer outra
    # terapia (ex.: TERAPIA ESPECIAL) fica NÃO mapeada -> alerta.
    if "TERAPIA" in alvo:
        return "consulta" if "SIMPLES" in alvo else None
    if "CONSULTA" in alvo:
        return "consulta"
    if "ESPECIAL" in alvo:
        return "especial"
    if "SIMPLES" in alvo:
        return "simples"
    return None  # não mapeado -> vira divergência (usuário alertado)


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
def _abrir_worksheet(conteudo: bytes):
    return load_workbook(BytesIO(conteudo), read_only=True, data_only=True).active


def _mapa_colunas(cabecalho: tuple[Any, ...]) -> dict[str, int]:
    mapa: dict[str, int] = {}
    for idx, valor in enumerate(cabecalho):
        chave = _norm_cabecalho(valor)
        if chave and chave not in mapa:
            mapa[chave] = idx
    return mapa


def _resolver_indices(mapa: dict[str, int], cols: Mapping[str, str | None]) -> dict[str, int | None]:
    return {
        c: (mapa.get(_norm_cabecalho(nome)) if nome else None)
        for c, nome in cols.items()
    }


def _cel(linha: tuple[Any, ...], idx: int | None) -> Any:
    return linha[idx] if idx is not None and idx < len(linha) else None


def _detectar_layout(cabecalho: tuple[Any, ...]) -> str | None:
    """Identifica a operadora (layout) pela assinatura de colunas."""
    mapa = _mapa_colunas(cabecalho)
    for operadora, cols in _LAYOUTS.items():
        idx = _resolver_indices(mapa, cols)
        if all(idx[c] is not None for c in _OBRIGATORIAS):
            return operadora
    return None


def _e_consolidado(cabecalho: tuple[Any, ...]) -> bool:
    return _detectar_layout(cabecalho) is not None


def ler_consolidado(nome_arquivo: str, conteudo: bytes) -> Consolidado:
    """Lê um Consolidado de coparticipação a partir dos bytes da planilha."""
    ws = _abrir_worksheet(conteudo)
    linhas = ws.iter_rows(values_only=True)
    cabecalho = next(linhas, ())
    operadora = _detectar_layout(cabecalho)
    if operadora is None:
        raise ValueError(
            f"Planilha '{nome_arquivo}' não parece um Consolidado de coparticipação "
            "(colunas não batem com o layout Unimed nem Bradesco)."
        )
    col = _resolver_indices(_mapa_colunas(cabecalho), _LAYOUTS[operadora])

    resultado = Consolidado(nome_arquivo=nome_arquivo)
    for linha in linhas:
        valor = _to_decimal(_cel(linha, col["valor_coparticipacao"]))
        cpf_titular = normalizar_cpf(_cel(linha, col["cpf_titular"]))
        procedimento = _texto(_cel(linha, col["procedimento"]))

        if valor is None:
            continue
        # Linha de total: só o valor somado, sem CPF nem procedimento.
        if not cpf_titular and not procedimento:
            resultado.total_informado = valor
            continue

        resultado.eventos.append(
            EventoCoparticipacao(
                cpf_titular=cpf_titular or "",
                nome_titular=_texto(_cel(linha, col["nome_titular"])),
                nome_beneficiario=_texto(_cel(linha, col["nome_beneficiario"])),
                tipo=_classificar_tipo(procedimento),
                procedimento=procedimento,
                valor_coparticipacao=valor,
                data_atendimento=_to_date(_cel(linha, col["data_atendimento"])),
                empresa=_texto(_cel(linha, col["nome_empresa"])) or None,
                operadora=operadora,
            )
        )
    return resultado


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------
def _arquivos_planilha(arquivos: dict[str, bytes]) -> dict[str, bytes]:
    return {
        nome: conteudo
        for nome, conteudo in arquivos.items()
        if nome.lower().endswith(EXTENSOES_PLANILHA)
    }


def validar_estrutura(arquivos: dict[str, bytes]) -> tuple[list[str], list[str]]:
    """Confere a estrutura dos Consolidados; acumula todos os problemas."""
    erros: list[str] = []
    alertas: list[str] = []
    planilhas = _arquivos_planilha(arquivos)
    if not planilhas:
        erros.append("Nenhum Consolidado (.xlsx) foi enviado.")
        return erros, alertas
    for nome, conteudo in planilhas.items():
        try:
            cabecalho = next(_abrir_worksheet(conteudo).iter_rows(values_only=True), ())
        except Exception as exc:  # noqa: BLE001
            erros.append(f"Não foi possível abrir '{nome}': {exc}")
            continue
        if not _e_consolidado(cabecalho):
            erros.append(
                f"Planilha '{nome}' não é um Consolidado de coparticipação reconhecido."
            )
    return erros, alertas


def ler(arquivos: dict[str, bytes], dados_externos: dict[str, Any]) -> list[Consolidado]:
    """Lê todos os Consolidados enviados (Unimed e/ou Bradesco, mesmo formato)."""
    return [
        ler_consolidado(nome, conteudo)
        for nome, conteudo in _arquivos_planilha(arquivos).items()
    ]
