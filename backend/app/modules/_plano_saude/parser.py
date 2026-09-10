"""
Leitura e normalização das PLANILHAS de valores do plano de saúde.

Responsabilidade (apenas FORMATO de arquivo — nada de regra de negócio):
transformar os bytes das planilhas mensais das operadoras em uma estrutura
Python limpa e uniforme (`PlanilhaValores`), pronta para o `calculator`.

Duas operadoras, dois layouts totalmente distintos:

- UNIMED: uma linha por vida, com `CPF_TITULAR`, `CPF_ASSOCIADO`, `DEPENDENCIA`
  (0 = titular; >0 = dependente) e `VALOR TOTAL`. A ligação dependente→titular
  já está na planilha (via `CPF_TITULAR`). Casa com a API por CPF.

- BRADESCO: NÃO tem CPF. A família é agrupada por `NUMERO DO CERTIFICADO`
  (`COMPLEMENTO DO CERTIFICADO` = "00" é o titular; >"00" é dependente) e o
  valor é `VALOR DO LANCAMENTO`. O vínculo com a API é feito depois, por NOME
  do titular (no calculator) — aqui o parser só extrai os nomes.

A operadora é identificada pela ASSINATURA DE COLUNAS (o nome do arquivo é
ignorado, pois o usuário nem sempre envia um nome claro).

Particularidades tratadas aqui:
- Linha de TOTAL no fim da planilha (ambas as operadoras) -> `total_informado`.
- Linhas ATÍPICAS do Bradesco (`NUMERO DO CERTIFICADO` = "0000000", ex.: taxas
  e ajustes) -> `atipicas`; não entram no rateio, mas são apresentadas ao
  usuário e contam na reconciliação do total.
- CPF sempre normalizado para 11 dígitos (corrige zeros à esquerda perdidos).
- Valores convertidos para `Decimal`; valores negativos (estornos) preservados.

Só arquivos de planilha (.xlsx/.xls) são tratados aqui. NFs e boletos (PDF)
são lidos no passo de reconciliação (validators), não neste parser.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from openpyxl import load_workbook

# Extensões consideradas planilha de valores (o resto — PDF — é ignorado aqui).
EXTENSOES_PLANILHA: tuple[str, ...] = (".xlsx", ".xls")


# ---------------------------------------------------------------------------
# Estruturas de saída (o que o calculator consome)
# ---------------------------------------------------------------------------
@dataclass
class LinhaValor:
    """
    Uma vida (titular ou dependente) com o valor mensal cobrado pela operadora.

    Campos preenchidos variam por operadora:
    - Unimed preenche `cpf`, `cpf_titular` e `matricula`.
    - Bradesco não tem CPF; identifica a família por `grupo_familiar`
      (= número do certificado) e depende do `nome`/`nome_titular` para casar
      com a API mais adiante.
    """

    operadora: str                 # "unimed" | "bradesco"
    competencia: str               # "AAAAMM", ex.: "202607"
    grupo_familiar: str            # chave de agregação da família
    is_titular: bool               # True = titular; False = dependente
    nome: str                      # nome da vida (titular ou dependente)
    valor: Decimal                 # valor mensal (pode ser negativo: estorno)
    nome_titular: str | None = None
    cpf: str | None = None         # CPF da vida (Unimed); None no Bradesco
    cpf_titular: str | None = None # Unimed; None no Bradesco
    matricula: str | None = None   # Unimed (FUNCIONAL); None no Bradesco
    empresa_planilha: str | None = None  # Unimed (NOME_EMPRESA) — só conferência


@dataclass
class LinhaAtipica:
    """
    Lançamento que NÃO se atribui a uma vida (ex.: Bradesco certificado
    "0000000" — taxas/ajustes). Fica fora do rateio, mas é apresentado ao
    usuário e entra na reconciliação do total faturado.
    """

    operadora: str
    descricao: str
    valor: Decimal


@dataclass
class PlanilhaValores:
    """Resultado da leitura de UMA planilha de operadora."""

    operadora: str
    competencia: str | None
    nome_arquivo: str
    linhas: list[LinhaValor] = field(default_factory=list)
    atipicas: list[LinhaAtipica] = field(default_factory=list)
    total_informado: Decimal | None = None  # linha de total da planilha


# ---------------------------------------------------------------------------
# Assinaturas de coluna (identificação da operadora)
# ---------------------------------------------------------------------------
# Nomes canônicos -> texto do cabeçalho esperado (comparado já normalizado).
_COLS_UNIMED = {
    "cod_empresa": "COD_EMPRESA",
    "competencia": "COMPETENCIA",
    "funcional": "FUNCIONAL",
    "dependencia": "DEPENDENCIA",
    "nome_associado": "NOME_ASSOCIADO",
    "cpf_associado": "CPF_ASSOCIADO",
    "nome_titular": "NOME_TITULAR",
    "cpf_titular": "CPF_TITULAR",
    "valor_total": "VALOR TOTAL",
    "nome_empresa": "NOME_EMPRESA",
}
_COLS_BRADESCO = {
    "certificado": "NUMERO DO CERTIFICADO",
    "complemento": "COMPLEMENTO DO CERTIFICADO",
    "nome": "NOME SEGURADO/DEPENDENTE",
    "grau_parentesco": "COD. GRAU PARENT.DEP.",
    "data_lancamento": "DATA DE LANCAMENTO",
    "valor_lancamento": "VALOR DO LANCAMENTO",
}

# Colunas que, se presentes, identificam a operadora sem ambiguidade.
_ASSINATURA_UNIMED = ("cpf_titular", "valor_total", "cod_empresa")
_ASSINATURA_BRADESCO = ("certificado", "valor_lancamento")


# ---------------------------------------------------------------------------
# Helpers de normalização
# ---------------------------------------------------------------------------
def _sem_acento(texto: str) -> str:
    forma = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in forma if not unicodedata.combining(c))


def _norm_cabecalho(valor: Any) -> str:
    """Normaliza um cabeçalho: sem acento, maiúsculo, sem pontuação, 1 espaço."""
    if valor is None:
        return ""
    texto = _sem_acento(str(valor)).upper()
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    return texto.strip()


def normalizar_cpf(valor: Any) -> str | None:
    """
    Deixa só os dígitos e completa com zeros à esquerda até 11 (corrige o
    caso comum de CPF que perde o zero inicial ao virar número na planilha).

    Retorna None quando não há dígitos. CPFs com mais de 11 dígitos são
    devolvidos como estão (o validator sinaliza), para não mascarar erro.
    """
    if valor is None:
        return None
    digitos = re.sub(r"\D", "", str(valor))
    if not digitos:
        return None
    return digitos.zfill(11) if len(digitos) <= 11 else digitos


_CENTAVOS = Decimal("0.01")


def _to_decimal(valor: Any) -> Decimal | None:
    """
    Converte número/string (formato pt-BR ou en) para Decimal; None se vazio.

    Valores vindos de `float` são quantizados para 2 casas: células de SOMA do
    Excel trazem artefatos (ex.: 7923.280000000002) que, sem isso, gerariam
    divergência falsa na reconciliação. Moeda em BRL tem 2 casas.
    """
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        # str() evita ampliar o erro binário; quantize remove o resíduo.
        return Decimal(str(valor)).quantize(_CENTAVOS, rounding=ROUND_HALF_UP)
    texto = str(valor).strip()
    if not texto:
        return None
    if "," in texto and "." in texto:
        # "1.234,56" -> ponto é milhar, vírgula é decimal.
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def _normalizar_competencia(valor: Any) -> str | None:
    """Normaliza a competência para 'AAAAMM' (aceita 202607 e 07/2026)."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    if "/" in texto:
        partes = texto.split("/")
        if len(partes) == 2:
            mes, ano = partes[0].strip().zfill(2), partes[1].strip()
            if len(ano) == 4:
                return f"{ano}{mes}"
    digitos = re.sub(r"\D", "", texto)
    if len(digitos) == 6:
        # Assume AAAAMM quando começa com século plausível; senão MMAAAA.
        return digitos if digitos[:2] in ("19", "20") else digitos[2:] + digitos[:2]
    return digitos or None


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


# ---------------------------------------------------------------------------
# Leitura de planilha
# ---------------------------------------------------------------------------
def _abrir_worksheet(conteudo: bytes):
    wb = load_workbook(BytesIO(conteudo), read_only=True, data_only=True)
    return wb.active


def _mapa_colunas(cabecalho: tuple[Any, ...]) -> dict[str, int]:
    """Mapa cabeçalho-normalizado -> índice da coluna (primeira ocorrência)."""
    mapa: dict[str, int] = {}
    for idx, valor in enumerate(cabecalho):
        chave = _norm_cabecalho(valor)
        if chave and chave not in mapa:
            mapa[chave] = idx
    return mapa


def _resolver_indices(
    mapa: dict[str, int], colunas: dict[str, str]
) -> dict[str, int | None]:
    """Para cada nome canônico, acha o índice pelo cabeçalho normalizado."""
    return {
        canonico: mapa.get(_norm_cabecalho(cabecalho))
        for canonico, cabecalho in colunas.items()
    }


def detectar_operadora(cabecalho: tuple[Any, ...]) -> str | None:
    """Identifica a operadora pela presença das colunas-assinatura."""
    mapa = _mapa_colunas(cabecalho)
    idx_uni = _resolver_indices(mapa, _COLS_UNIMED)
    if all(idx_uni[c] is not None for c in _ASSINATURA_UNIMED):
        return "unimed"
    idx_bra = _resolver_indices(mapa, _COLS_BRADESCO)
    if all(idx_bra[c] is not None for c in _ASSINATURA_BRADESCO):
        return "bradesco"
    return None


def _cel(linha: tuple[Any, ...], idx: int | None) -> Any:
    return linha[idx] if idx is not None and idx < len(linha) else None


def _ler_unimed(ws, nome_arquivo: str) -> PlanilhaValores:
    linhas_iter = ws.iter_rows(values_only=True)
    cabecalho = next(linhas_iter, ())
    col = _resolver_indices(_mapa_colunas(cabecalho), _COLS_UNIMED)

    resultado = PlanilhaValores(
        operadora="unimed", competencia=None, nome_arquivo=nome_arquivo
    )
    for linha in linhas_iter:
        valor = _to_decimal(_cel(linha, col["valor_total"]))
        cpf_titular = normalizar_cpf(_cel(linha, col["cpf_titular"]))
        cod_empresa = _texto(_cel(linha, col["cod_empresa"]))

        if valor is None:
            continue
        # Linha de total: sem CPF_TITULAR e sem COD_EMPRESA, só o valor somado.
        if not cpf_titular and not cod_empresa:
            resultado.total_informado = valor
            continue

        competencia = _normalizar_competencia(_cel(linha, col["competencia"]))
        if competencia and resultado.competencia is None:
            resultado.competencia = competencia

        dependencia = _texto(_cel(linha, col["dependencia"]))
        resultado.linhas.append(
            LinhaValor(
                operadora="unimed",
                competencia=competencia or "",
                grupo_familiar=cpf_titular or "",
                is_titular=dependencia in ("0", "0.0", ""),
                nome=_texto(_cel(linha, col["nome_associado"])),
                nome_titular=_texto(_cel(linha, col["nome_titular"])) or None,
                cpf=normalizar_cpf(_cel(linha, col["cpf_associado"])),
                cpf_titular=cpf_titular,
                matricula=_texto(_cel(linha, col["funcional"])) or None,
                empresa_planilha=_texto(_cel(linha, col["nome_empresa"])) or None,
                valor=valor,
            )
        )
    return resultado


def _ler_bradesco(ws, nome_arquivo: str) -> PlanilhaValores:
    linhas_iter = ws.iter_rows(values_only=True)
    cabecalho = next(linhas_iter, ())
    col = _resolver_indices(_mapa_colunas(cabecalho), _COLS_BRADESCO)

    resultado = PlanilhaValores(
        operadora="bradesco", competencia=None, nome_arquivo=nome_arquivo
    )
    for linha in linhas_iter:
        valor = _to_decimal(_cel(linha, col["valor_lancamento"]))
        certificado = _texto(_cel(linha, col["certificado"]))
        nome = _texto(_cel(linha, col["nome"]))

        if valor is None:
            continue
        # Linha de total: sem certificado e sem nome, só o valor somado.
        if not certificado and not nome:
            resultado.total_informado = valor
            continue

        competencia = _normalizar_competencia(_cel(linha, col["data_lancamento"]))
        if competencia and resultado.competencia is None:
            resultado.competencia = competencia

        # Certificado "0000000" (só zeros) = lançamento atípico (taxa/ajuste).
        if not certificado.strip("0"):
            resultado.atipicas.append(
                LinhaAtipica(
                    operadora="bradesco",
                    descricao=nome or "Lançamento sem certificado",
                    valor=valor,
                )
            )
            continue

        complemento = _texto(_cel(linha, col["complemento"]))
        resultado.linhas.append(
            LinhaValor(
                operadora="bradesco",
                competencia=competencia or "",
                grupo_familiar=certificado,
                is_titular=complemento.strip("0") == "",
                nome=nome,
                valor=valor,
            )
        )

    _preencher_nome_titular_bradesco(resultado.linhas)
    return resultado


def _preencher_nome_titular_bradesco(linhas: list[LinhaValor]) -> None:
    """Resolve o nome do titular de cada certificado (linha COMPLEMENTO '00')."""
    titular_por_grupo = {
        l.grupo_familiar: l.nome for l in linhas if l.is_titular
    }
    for linha in linhas:
        linha.nome_titular = titular_por_grupo.get(linha.grupo_familiar)


_LEITORES = {"unimed": _ler_unimed, "bradesco": _ler_bradesco}


def ler_planilha(nome_arquivo: str, conteudo: bytes) -> PlanilhaValores:
    """Lê uma planilha de valores, detectando a operadora pela assinatura."""
    ws = _abrir_worksheet(conteudo)
    operadora = detectar_operadora(next(ws.iter_rows(values_only=True), ()))
    if operadora is None:
        raise ValueError(
            f"Não foi possível identificar a operadora da planilha '{nome_arquivo}' "
            "(assinatura de colunas não reconhecida)."
        )
    # Reabre para ler do início (o iterador do cabeçalho já foi consumido).
    ws = _abrir_worksheet(conteudo)
    return _LEITORES[operadora](ws, nome_arquivo)


# ---------------------------------------------------------------------------
# API pública consumida pelo module.py
# ---------------------------------------------------------------------------
def _arquivos_planilha(arquivos: dict[str, bytes]) -> dict[str, bytes]:
    """Filtra apenas os arquivos de planilha (.xlsx/.xls); ignora PDFs."""
    return {
        nome: conteudo
        for nome, conteudo in arquivos.items()
        if nome.lower().endswith(EXTENSOES_PLANILHA)
    }


def operadoras_presentes(arquivos: dict[str, bytes]) -> set[str]:
    """
    Detecta quais operadoras têm planilha entre os arquivos (pela assinatura de
    colunas). Usado pelos módulos para exigir a planilha da sua operadora.
    """
    return {op for op in classificar_planilhas(arquivos).values() if op}


def classificar_planilhas(arquivos: dict[str, bytes]) -> dict[str, str | None]:
    """
    Classifica cada arquivo de planilha (.xlsx/.xls) pela operadora detectada.

    Valor: nome da operadora ("unimed"/"bradesco") ou None quando o arquivo é
    ilegível ou não corresponde a nenhuma operadora conhecida.
    """
    resultado: dict[str, str | None] = {}
    for nome, conteudo in _arquivos_planilha(arquivos).items():
        try:
            cabecalho = next(_abrir_worksheet(conteudo).iter_rows(values_only=True), ())
        except Exception:  # noqa: BLE001 — ilegível vira "não reconhecida"
            resultado[nome] = None
            continue
        resultado[nome] = detectar_operadora(cabecalho)
    return resultado


def colunas_faltando(arquivos: dict[str, bytes], operadora: str) -> list[str]:
    """
    Para as planilhas da `operadora` informada, retorna mensagens de erro sobre
    colunas obrigatórias ausentes (uma por planilha com problema).
    """
    colunas = _COLS_UNIMED if operadora == "unimed" else _COLS_BRADESCO
    erros: list[str] = []
    for nome, conteudo in _arquivos_planilha(arquivos).items():
        try:
            cabecalho = next(_abrir_worksheet(conteudo).iter_rows(values_only=True), ())
        except Exception:  # noqa: BLE001
            continue
        if detectar_operadora(cabecalho) != operadora:
            continue
        indices = _resolver_indices(_mapa_colunas(cabecalho), colunas)
        faltando = [colunas[c] for c, idx in indices.items() if idx is None]
        if faltando:
            erros.append(
                f"Planilha '{nome}' ({operadora}): colunas obrigatórias "
                f"ausentes: {', '.join(faltando)}."
            )
    return erros


def validar_estrutura(arquivos: dict[str, bytes]) -> tuple[list[str], list[str]]:
    """
    Confere a estrutura das planilhas sem executar o cálculo.

    Acumula TODOS os problemas de uma vez (não para no primeiro):
    - nenhuma planilha enviada;
    - planilha ilegível;
    - operadora não reconhecida pela assinatura de colunas;
    - colunas obrigatórias faltando para a operadora identificada.

    Returns:
        (erros, alertas) para o module montar o ValidationResult.
    """
    erros: list[str] = []
    alertas: list[str] = []

    planilhas = _arquivos_planilha(arquivos)
    if not planilhas:
        erros.append("Nenhuma planilha de valores (.xlsx) foi enviada.")
        return erros, alertas

    for nome, conteudo in planilhas.items():
        try:
            cabecalho = next(_abrir_worksheet(conteudo).iter_rows(values_only=True), ())
        except Exception as exc:  # noqa: BLE001 — reporta como erro de estrutura
            erros.append(f"Não foi possível abrir a planilha '{nome}': {exc}")
            continue

        operadora = detectar_operadora(cabecalho)
        if operadora is None:
            erros.append(
                f"Planilha '{nome}': operadora não reconhecida "
                "(colunas não batem com Unimed nem Bradesco)."
            )
            continue

        colunas = _COLS_UNIMED if operadora == "unimed" else _COLS_BRADESCO
        indices = _resolver_indices(_mapa_colunas(cabecalho), colunas)
        faltando = [colunas[c] for c, idx in indices.items() if idx is None]
        if faltando:
            erros.append(
                f"Planilha '{nome}' ({operadora}): colunas obrigatórias "
                f"ausentes: {', '.join(faltando)}."
            )

    return erros, alertas


def ler(
    arquivos: dict[str, bytes],
    dados_externos: dict[str, Any],
) -> list[PlanilhaValores]:
    """
    Lê e normaliza todas as planilhas de valores enviadas.

    Deve ser chamado após `validar_estrutura` indicar ausência de erros.

    Args:
        arquivos: mapa nome_do_arquivo -> bytes (planilhas e PDFs; PDFs
                  são ignorados aqui).
        dados_externos: não utilizado nesta etapa (a API entra no calculator).

    Returns:
        list[PlanilhaValores] — uma entrada por planilha lida.
    """
    return [
        ler_planilha(nome, conteudo)
        for nome, conteudo in _arquivos_planilha(arquivos).items()
    ]
