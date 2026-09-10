"""
Reconciliação do rateio com os documentos fiscais (NF Unimed / boleto Bradesco).

Responsabilidade: extrair o valor total faturado de cada documento em PDF e
compará-lo com o resultado do rateio (`ResultadoRateio`), gerando ALERTAS (não
bloqueantes) quando os valores não batem. É a etapa que responde "a soma que
vamos lançar confere com o que a operadora cobrou?".

Só a Unimed emite NF (NFS-e); o Bradesco envia boleto. Ambos são PDFs digitais
(texto selecionável), lidos com `pypdf` — sem OCR. O tipo do documento e a
empresa (Vertex / Aurora / Zenith) são identificados pelo CONTEÚDO, não pelo
nome do arquivo.

Nota de negócio: o `VALOR TOTAL DO SERVIÇO` da NF inclui itens além da
mensalidade por vida (inscrição, 2ª via, retroativa, devolução/exclusão). Logo,
uma diferença para a soma da planilha pode ser legítima — por isso o resultado
é um alerta com os dois valores e a diferença, para o usuário avaliar, e não um
erro que trava o processo.

Este módulo é puro: recebe bytes e o resultado já calculado; não acessa rede
nem banco.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from pypdf import PdfReader

from .calculator import ResultadoRateio

EXTENSAO_PDF = ".pdf"
# Tolerância para considerar que os valores "batem" (centavos de arredondamento).
TOLERANCIA = Decimal("0.01")

# Identificação da empresa por palavra-chave no texto e por CNPJ.
_EMPRESAS_POR_NOME = {
    "ZENITH": "Zenith",
    "VERTEX": "Vertex",
    "Aurora": "Aurora",
}
_EMPRESAS_POR_CNPJ = {
    "23.456.780/0001-84": "Vertex",
    "12.345.670/0001-29": "Aurora",
    "34.567.890/0001-30": "Zenith",
}
# CNPJs das operadoras (para separar prestador de tomador).
_CNPJ_UNIMED = "45.678.910/0001-66"
_CNPJ_BRADESCO = "56.789.120/0001-74"


def configurar(
    empresas_por_nome: dict[str, str] | None = None,
    empresas_por_cnpj: dict[str, str] | None = None,
    cnpj_operadora: dict[str, str] | None = None,
) -> None:
    """Sobrepõe os mapas de empresa/operadora com os do CADASTRO (banco).

    Chamado no startup após o seed. Os literais acima ficam como fallback (para
    testes/uso puro sem banco). Edições no cadastro refletem no próximo restart.
    """
    global _EMPRESAS_POR_NOME, _EMPRESAS_POR_CNPJ, _CNPJ_UNIMED, _CNPJ_BRADESCO
    if empresas_por_nome:
        _EMPRESAS_POR_NOME = dict(empresas_por_nome)
    if empresas_por_cnpj:
        _EMPRESAS_POR_CNPJ = dict(empresas_por_cnpj)
    if cnpj_operadora:
        if cnpj_operadora.get("unimed"):
            _CNPJ_UNIMED = cnpj_operadora["unimed"]
        if cnpj_operadora.get("bradesco"):
            _CNPJ_BRADESCO = cnpj_operadora["bradesco"]

_RE_CNPJ = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
# Valor monetário pt-BR: 1.234,56 / -8.703,8 / 45,00 (para na parte decimal).
_RE_VALOR = r"(-?\d[\d.]*,\d+)"


# ---------------------------------------------------------------------------
# Estruturas
# ---------------------------------------------------------------------------
@dataclass
class DocumentoFatura:
    """Total faturado extraído de um documento fiscal (NF ou boleto)."""

    operadora: str                 # "unimed" | "bradesco"
    tipo: str                      # "nf" | "boleto"
    nome_arquivo: str
    valor_total: Decimal
    empresa: str | None = None     # "Vertex" | "Aurora" | "Zenith"
    cnpj_tomador: str | None = None
    itens: dict[str, Decimal] = field(default_factory=dict)  # detalhamento (NF)
    # Metadados da NFS-e (usados na pré-nota da Zenith): número, data (AAAAMMDD), série.
    numero: str | None = None
    emissao: str | None = None
    serie: str | None = None
    vencimento: str | None = None   # dd/mm/aaaa (para a notificação ao fiscal)


@dataclass
class AlertaReconciliacao:
    """Comparação entre o total de um documento (NF/boleto) e o total faturado
    na planilha para a mesma empresa."""

    operadora: str
    empresa: str | None
    valor_documento: Decimal
    valor_base: Decimal       # base de comparação p/ a empresa (planilha ou rateio via API)
    diferenca: Decimal
    bate: bool
    mensagem: str
    # Metadados do documento (NF) — usados no lançamento (pré-nota) e na notificação.
    numero_documento: str | None = None
    emissao_documento: str | None = None
    serie_documento: str | None = None
    vencimento_documento: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _valor_br(texto: str | None) -> Decimal | None:
    if not texto:
        return None
    limpo = texto.strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(limpo)
    except InvalidOperation:
        return None


def _norm(texto: Any) -> str:
    if texto is None:
        return ""
    forma = unicodedata.normalize("NFKD", str(texto)).upper()
    sem_acento = "".join(c for c in forma if not unicodedata.combining(c))
    return " ".join(sem_acento.split())


def _texto_pdf(conteudo: bytes) -> str:
    reader = PdfReader(BytesIO(conteudo))
    return "\n".join((pagina.extract_text() or "") for pagina in reader.pages)


def _detectar_empresa(texto: str, cnpjs: list[str]) -> str | None:
    alvo = _norm(texto)
    for chave, empresa in _EMPRESAS_POR_NOME.items():
        if chave in alvo:
            return empresa
    for cnpj in cnpjs:
        if cnpj in _EMPRESAS_POR_CNPJ:
            return _EMPRESAS_POR_CNPJ[cnpj]
    return None


# ---------------------------------------------------------------------------
# Extratores por documento
# ---------------------------------------------------------------------------
def _extrair_boleto_bradesco(texto: str, nome: str) -> DocumentoFatura:
    # Âncora principal: "cobrar o valor de R$ X"; fallback: valor mascarado "***X".
    m = re.search(r"cobrar o valor de R\$\s*" + _RE_VALOR, texto)
    if not m:
        m = re.search(r"\*+\s*" + _RE_VALOR, texto)
    valor = _valor_br(m.group(1)) if m else None

    cnpjs = _RE_CNPJ.findall(texto)
    tomador = next((c for c in cnpjs if c != _CNPJ_BRADESCO), None)
    return DocumentoFatura(
        operadora="bradesco",
        tipo="boleto",
        nome_arquivo=nome,
        valor_total=valor if valor is not None else Decimal("0"),
        empresa=_detectar_empresa(texto, cnpjs),
        cnpj_tomador=tomador,
    )


def _secao_detalhamento(texto: str) -> str:
    """Isola a seção 'OUTRAS INFORMAÇÕES' (detalhamento da fatura), parando na
    linha de tributo aproximado, que não é item da fatura."""
    alvo = _norm(texto)
    inicio = alvo.find("OUTRAS INFORMA")
    if inicio == -1:
        return texto
    trecho = texto[inicio:]
    corte = _norm(trecho).find("TRIBUTO INCLUSO")
    return trecho[:corte] if corte != -1 else trecho


def _extrair_meta_nfse(texto: str) -> tuple[str | None, str | None, str | None, str | None]:
    """Extrai (número, emissão AAAAMMDD, série, vencimento dd/mm/aaaa) da NFS-e.
    Âncoras: número = 1ª linha só-dígitos (nº da nota, no topo); emissão = 1ª data
    dd/mm/aaaa; série = 'Série NNNN'; vencimento = 'vencimento: dd/mm/aaaa'."""
    m_num = re.search(r"(?m)^\s*(\d{6,10})\s*$", texto)
    numero = m_num.group(1) if m_num else None
    m_dt = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto)
    emissao = f"{m_dt.group(3)}{m_dt.group(2)}{m_dt.group(1)}" if m_dt else None
    m_serie = re.search(r"S[ée]rie\s*(\d+)", texto, re.IGNORECASE)
    serie = m_serie.group(1) if m_serie else None
    m_venc = re.search(r"vencimento[:\s]*(\d{2}/\d{2}/\d{4})", texto, re.IGNORECASE)
    vencimento = m_venc.group(1) if m_venc else None
    return numero, emissao, serie, vencimento


def _extrair_nf_unimed(texto: str, nome: str) -> DocumentoFatura:
    # Detalhamento em "OUTRAS INFORMAÇÕES": pares "<rótulo> R$ <valor>".
    itens: dict[str, Decimal] = {}
    for rotulo, bruto in re.findall(
        r"([A-Za-zÀ-ÿ0-9 ]+?) R\$\s*" + _RE_VALOR, _secao_detalhamento(texto)
    ):
        valor = _valor_br(bruto)
        if valor is not None:
            itens[rotulo.strip()] = valor

    # Total: preferir "TOTAL R$ X"; senão soma dos itens conhecidos.
    total = itens.get("TOTAL")
    if total is None:
        m = re.search(r"\bTOTAL R\$\s*" + _RE_VALOR, texto)
        total = _valor_br(m.group(1)) if m else None

    cnpjs = _RE_CNPJ.findall(texto)
    tomador = next((c for c in cnpjs if c not in (_CNPJ_UNIMED,)), None)
    numero, emissao, serie, vencimento = _extrair_meta_nfse(texto)
    return DocumentoFatura(
        operadora="unimed",
        tipo="nf",
        nome_arquivo=nome,
        valor_total=total if total is not None else Decimal("0"),
        empresa=_detectar_empresa(texto, cnpjs),
        cnpj_tomador=tomador,
        itens=itens,
        numero=numero,
        emissao=emissao,
        serie=serie,
        vencimento=vencimento,
    )


def _extrair_boleto_unimed(texto: str, nome: str) -> DocumentoFatura:
    """
    Fatura de serviços da Unimed (nota + ficha de compensação no mesmo PDF).

    Traz o mesmo total da NFS-e; usamos o "TOTAL <valor>" do detalhamento. O
    número/série da nota vêm da NFS-e (documento próprio), não daqui — por isso a
    reconciliação prefere a NF quando ambos são enviados.
    """
    m = re.search(r"\bTOTAL\s+R?\$?\s*" + _RE_VALOR, texto)
    total = _valor_br(m.group(1)) if m else None
    cnpjs = _RE_CNPJ.findall(texto)
    tomador = next((c for c in cnpjs if c != _CNPJ_UNIMED), None)
    _, _, _, vencimento = _extrair_meta_nfse(texto)
    return DocumentoFatura(
        operadora="unimed",
        tipo="boleto",
        nome_arquivo=nome,
        valor_total=total if total is not None else Decimal("0"),
        empresa=_detectar_empresa(texto, cnpjs),
        cnpj_tomador=tomador,
        vencimento=vencimento,
    )


def extrair_documento(nome: str, conteudo: bytes) -> DocumentoFatura | None:
    """Extrai um documento fiscal de um PDF; None se não for NF/boleto conhecido."""
    if not nome.lower().endswith(EXTENSAO_PDF):
        return None
    texto = _texto_pdf(conteudo)
    alvo = _norm(texto)
    # Estrutura de boleto (ficha de compensação) é inconfundível. A fatura Unimed
    # traz TANTO "nota fiscal" QUANTO ficha de compensação — por isso o boleto é
    # avaliado ANTES da NFS-e, para não confundir a fatura/boleto com a nota.
    if _tem_estrutura_boleto(alvo):
        if "BRADESCO" in alvo:
            return _extrair_boleto_bradesco(texto, nome)
        if "UNIMED" in alvo:
            return _extrair_boleto_unimed(texto, nome)
    if "UNIMED" in alvo and "NFS" in alvo:
        return _extrair_nf_unimed(texto, nome)
    if "BRADESCO" in alvo:
        return _extrair_boleto_bradesco(texto, nome)
    return None


def extrair_documentos(arquivos: dict[str, bytes]) -> list[DocumentoFatura]:
    """Extrai todos os documentos fiscais (PDF) enviados."""
    documentos = []
    for nome, conteudo in arquivos.items():
        doc = extrair_documento(nome, conteudo)
        if doc is not None:
            documentos.append(doc)
    return documentos


def classificar_documentos(arquivos: dict[str, bytes]) -> dict[str, tuple[str, str] | None]:
    """
    Classifica cada arquivo PDF: (operadora, tipo) se reconhecido como NF/boleto,
    ou None se for um PDF não reconhecido. Não-PDFs são ignorados aqui.
    """
    resultado: dict[str, tuple[str, str] | None] = {}
    for nome, conteudo in arquivos.items():
        if not nome.lower().endswith(EXTENSAO_PDF):
            continue
        doc = extrair_documento(nome, conteudo)
        resultado[nome] = (doc.operadora, doc.tipo) if doc else None
    return resultado


# Marcadores de texto para classificar um PDF de forma GENÉRICA (independente de
# operadora/banco) quando o extrator específico não reconhece o documento.
# Boleto: termos padrão de ficha de compensação (Febraban), presentes em qualquer
# banco (inclusive a fatura/boleto Unimed). NFS-e: "NFS" é o marcador forte —
# "NOTA FISCAL" sozinho é fraco (a fatura/boleto Unimed também o contém).
_MARCADORES_BOLETO = (
    "FICHA DE COMPENSACAO",
    "NOSSO NUMERO",
    "LINHA DIGITAVEL",
    "LOCAL DE PAGAMENTO",
    "LOCAL DO PAGAMENTO",
    "VALOR COBRADO",
    "CEDENTE",
)
_MARCADORES_NF = ("NFS", "NOTA FISCAL")


def _tem_estrutura_boleto(alvo: str) -> bool:
    """True se o texto (já normalizado) tem estrutura de ficha de compensação."""
    return any(m in alvo for m in _MARCADORES_BOLETO)


def classificar_pdf(nome: str, conteudo: bytes) -> str | None:
    """
    Classifica um PDF como "nf" ou "boleto" (None se não parecer nenhum).

    Primeiro tenta o extrator específico (NF/boleto Unimed e boleto Bradesco, que
    leem os valores). Se a operadora não for reconhecida, cai numa detecção
    genérica por marcadores — boleto ANTES de NF, pois uma fatura/boleto pode
    conter texto de "nota fiscal" além da ficha de compensação.
    """
    if not nome.lower().endswith(EXTENSAO_PDF):
        return None
    doc = extrair_documento(nome, conteudo)
    if doc is not None:
        return doc.tipo
    alvo = _norm(_texto_pdf(conteudo))
    if _tem_estrutura_boleto(alvo):
        return "boleto"
    if any(m in alvo for m in _MARCADORES_NF):
        return "nf"
    return None


# ---------------------------------------------------------------------------
# Reconciliação
# ---------------------------------------------------------------------------
def _alerta(
    operadora: str, empresa: str | None, tipo: str,
    valor_doc: Decimal, valor_final: Decimal,
    numero: str | None = None, emissao: str | None = None, serie: str | None = None,
    vencimento: str | None = None,
) -> AlertaReconciliacao:
    diferenca = valor_doc - valor_final
    bate = abs(diferenca) <= TOLERANCIA
    rotulo = empresa or "(empresa não identificada)"
    if bate:
        msg = f"{operadora}/{rotulo}: o valor final a lançar confere com o {tipo} (R$ {valor_doc})."
    else:
        msg = (
            f"{operadora}/{rotulo}: valor final R$ {valor_final} ≠ {tipo} R$ {valor_doc} "
            f"(diferença R$ {diferenca}) — verificar divergências não rateadas."
        )
    return AlertaReconciliacao(
        operadora=operadora, empresa=empresa, valor_documento=valor_doc,
        valor_base=valor_final, diferenca=diferenca, bate=bate, mensagem=msg,
        numero_documento=numero, emissao_documento=emissao, serie_documento=serie,
        vencimento_documento=vencimento,
    )


def _valor_final_por_empresa(resultado: ResultadoRateio) -> dict[str, Decimal]:
    """
    Valor final a lançar por empresa = rateado (itens por CC) + estornos.

    O estorno já vem abatido na NF/boleto; por isso ele compõe o valor final que
    deve bater com o documento. Estornos usam a empresa do NOME_EMPRESA da
    planilha; itens usam a empresa da API.
    """
    base: dict[str, Decimal] = {}
    for item in resultado.itens:
        chave = _norm(item.empresa)
        base[chave] = base.get(chave, Decimal("0")) + item.valor
    for estorno in resultado.estornos:
        chave = _norm(estorno.empresa)
        base[chave] = base.get(chave, Decimal("0")) + estorno.valor
    return base


def reconciliar(
    resultado: ResultadoRateio,
    documentos: list[DocumentoFatura],
) -> list[AlertaReconciliacao]:
    """
    Contra-prova: o VALOR FINAL a lançar por empresa (rateado + estornos) deve
    ser igual ao documento — NF (Unimed) ou boleto (Bradesco) — da mesma empresa.

    O estorno já está abatido na NF/boleto, então entra no valor final. Se ainda
    não bater, a diferença são divergências não rateadas (titulares não
    encontrados) ou erro de extração — sinalizado ao usuário.
    """
    valor_final = _valor_final_por_empresa(resultado)
    # Uma reconciliação por (operadora, empresa). A Unimed emite NF (NFS-e) e
    # fatura/boleto com o MESMO total; sem isto a empresa apareceria duas vezes e
    # o boleto (sem número de nota) sobrescreveria a NF na notificação ao fiscal.
    # A NF prevalece — carrega número/série/emissão usados na pré-nota e no e-mail.
    preferidos: dict[tuple[str, str], DocumentoFatura] = {}
    for doc in documentos:
        chave = (doc.operadora, _norm(doc.empresa))
        atual = preferidos.get(chave)
        if atual is None or (atual.tipo != "nf" and doc.tipo == "nf"):
            preferidos[chave] = doc
    return [
        _alerta(
            doc.operadora, doc.empresa, doc.tipo, doc.valor_total,
            valor_final.get(_norm(doc.empresa), Decimal("0")),
            numero=doc.numero, emissao=doc.emissao, serie=doc.serie,
            vencimento=doc.vencimento,
        )
        for doc in preferidos.values()
    ]


def validar_documentos(
    arquivos: dict[str, bytes],
    resultado: ResultadoRateio,
) -> tuple[list[DocumentoFatura], list[AlertaReconciliacao]]:
    """
    Orquestra a reconciliação: extrai os PDFs e compara com o resultado.

    Returns:
        (documentos, alertas) — os documentos extraídos e os alertas de
        reconciliação para compor o resultado/ValidationResult no module.
    """
    documentos = extrair_documentos(arquivos)
    return documentos, reconciliar(resultado, documentos)
