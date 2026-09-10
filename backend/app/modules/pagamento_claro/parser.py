"""
Leitura do boleto/fatura da Claro (PDF) — telefonia móvel.

Responsabilidade (apenas FORMATO): transformar os bytes de UM PDF da Claro em
um `BoletoClaro` — cabeçalho (conta, vencimento, valor, dados da NFCOM) mais uma
`LinhaBoleto` por celular, já com o valor cobrado e a composição desse valor.

Aqui NÃO há cálculo de rateio: a Claro já entrega o valor de cada linha. O que o
parser faz é ler, somar a composição de cada linha e conferir contra o total do
boleto.

Estrutura do PDF (validada contra `dados/claro/SP_29LINHAS_JULHO.pdf`):

    pág. 1   resumo da conta: nº da conta/cliente, período de uso, vencimento,
             "Total a pagar R$ x" e a linha digitável.
    pág. 3   DANFE-COM (NFCOM): número, série, emissão, chave de acesso.
    pág. 5+  um bloco por celular, iniciado por
             "DETALHAMENTO DE LIGAÇÕES E SERVIÇOS DO CELULAR (11) 9xxxx xxxx",
             contendo:
               - "Mensalidades e Pacotes Promocionais": um item por
                 plano/pacote e um "TOTAL R$ x" de fechamento;
               - seções de uso (interurbanas, locais, fixos, internet, ...),
                 cada uma encerrada por "Total"/"Subtotal" cuja ÚLTIMA coluna é
                 o "Valor Cobrado" — é dali que sai o EXCEDENTE da linha.

    valor da linha = TOTAL das mensalidades + Σ valor cobrado das seções de uso
    Σ valor das linhas == "Total a pagar" (conferido em `BoletoClaro.confere`)

Blocos do mesmo celular repetidos (continuação entre páginas) são FUNDIDOS: os
serviços são acumulados numa única `LinhaBoleto`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

from pypdf import PdfReader

EXTENSOES_BOLETO: tuple[str, ...] = (".pdf",)

# Composição do valor de uma linha: mensalidade (plano/pacote) ou uso (excedente).
CATEGORIA_MENSALIDADE = "mensalidade"
CATEGORIA_USO = "uso"


# ---------------------------------------------------------------------------
# Estruturas de saída
# ---------------------------------------------------------------------------
@dataclass
class ServicoLinha:
    """Um componente do valor de uma linha (uma mensalidade ou uma seção de uso)."""

    descricao: str
    categoria: str  # CATEGORIA_MENSALIDADE | CATEGORIA_USO
    valor: Decimal


@dataclass
class AjusteBoleto:
    """
    Lançamento da CONTA, não de uma linha (seção "Outros Lançamentos").

    Ex.: "Desconto Créditos Anteriores -9,02" — crédito de faturas passadas. Não
    aparece no detalhamento de nenhum celular, então a soma das linhas fica maior
    (ou menor) que o total a pagar enquanto ele não for somado.

    A seção é lida por INTEIRO, item a item: multa, juros, estorno ou o que a
    operadora inventar entram sozinhos, sem precisar mexer no código.
    """

    descricao: str
    valor: Decimal  # negativo em créditos/descontos


@dataclass
class CategoriaBoleto:
    """
    Uma linha do resumo "Veja aqui o que está sendo cobrado" (pág. 1).

    Serve para DIAGNÓSTICO: quando a conferência não fecha, é a decomposição que
    o próprio boleto declara que aponta qual categoria não foi contemplada.
    """

    descricao: str
    valor: Decimal


@dataclass
class LinhaBoleto:
    """Um celular do boleto, com o valor cobrado e sua composição."""

    numero: str            # somente dígitos, com DDD: "11947703500"
    numero_exibicao: str   # como aparece no boleto: "(11) 94770 3500"
    servicos: list[ServicoLinha] = field(default_factory=list)

    @property
    def valor(self) -> Decimal:
        """Valor cobrado da linha = soma da composição (mensalidades + uso)."""
        return sum((s.valor for s in self.servicos), Decimal("0"))

    @property
    def valor_mensalidades(self) -> Decimal:
        return sum(
            (s.valor for s in self.servicos if s.categoria == CATEGORIA_MENSALIDADE),
            Decimal("0"),
        )

    @property
    def valor_uso(self) -> Decimal:
        """Excedente: o que foi cobrado além das mensalidades."""
        return sum(
            (s.valor for s in self.servicos if s.categoria == CATEGORIA_USO),
            Decimal("0"),
        )


@dataclass
class BoletoClaro:
    """Um boleto/fatura da Claro: o cabeçalho e as linhas nele detalhadas."""

    nome_arquivo: str
    conta: str = ""                  # nº da conta Claro — identifica o boleto
    cliente: str = ""                # nº do cliente
    razao_social: str = ""           # tomador (empresa)
    cnpj_tomador: str = ""
    vencimento: date | None = None
    emissao: date | None = None      # emissão da NFCOM
    competencia: str = ""            # referência, "MM/AAAA"
    periodo_inicio: date | None = None
    periodo_fim: date | None = None
    valor_total: Decimal | None = None  # "Total a pagar" impresso no boleto
    linha_digitavel: str = ""
    nfcom_numero: str = ""
    nfcom_serie: str = ""
    nfcom_chave: str = ""
    linhas: list[LinhaBoleto] = field(default_factory=list)
    ajustes: list[AjusteBoleto] = field(default_factory=list)
    categorias: list[CategoriaBoleto] = field(default_factory=list)

    @property
    def valor_linhas(self) -> Decimal:
        """Soma dos valores das linhas detalhadas."""
        return sum((l.valor for l in self.linhas), Decimal("0"))

    @property
    def valor_ajustes(self) -> Decimal:
        """Soma dos lançamentos de conta (negativa quando há crédito)."""
        return sum((a.valor for a in self.ajustes), Decimal("0"))

    @property
    def diferenca(self) -> Decimal:
        """
        Total impresso − (linhas + ajustes). Zero = boleto fecha.

        Diferente de zero significa que existe no boleto uma cobrança que não
        está no detalhamento das linhas nem em "Outros Lançamentos" — algo novo,
        que precisa ser entendido antes de lançar.
        """
        if self.valor_total is None:
            return Decimal("0")
        return self.valor_total - self.valor_linhas - self.valor_ajustes

    @property
    def confere(self) -> bool:
        """True quando linhas + ajustes batem exatamente com o total do boleto."""
        return self.valor_total is not None and self.diferenca == 0

    def resumo_categorias(self) -> str:
        """Decomposição declarada na pág. 1, em uma linha (para diagnóstico)."""
        return " | ".join(f"{c.descricao}: R$ {c.valor}" for c in self.categorias)


class BoletoInvalido(ValueError):
    """PDF ilegível ou fora do layout esperado da Claro."""


# ---------------------------------------------------------------------------
# Padrões do layout
# ---------------------------------------------------------------------------
# "DETALHAMENTO DE LIGAÇÕES E SERVIÇOS DO CELULAR (11) 94770 3500"
_RE_BLOCO = re.compile(
    r"^DETALHAMENTO DE LIGA\w+ES E SERVI\w+OS DO CELULAR\s*\((\d{2})\)\s*([\d ]+?)\s*$"
)
# Valor monetário brasileiro: 1.640,58 / 47,90 / -12,00
_RE_MOEDA = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}")
# Item de mensalidade: "Plano Claro Max 2.0 37,90"
_RE_ITEM_MENSALIDADE = re.compile(r"^(?P<descricao>.+?)\s+(?P<valor>-?\d{1,3}(?:\.\d{3})*,\d{2})$")
# Fechamento das mensalidades: "TOTAL R$ 47,90"
_RE_TOTAL_MENSALIDADES = re.compile(r"^TOTAL\s+R\$\s*(-?\d{1,3}(?:\.\d{3})*,\d{2})\s*$")
# Fechamento de seção de uso: "Total 00:01:42 00:01:42 0,00 0,00" / "Subtotal 10.058,257 0,00"
_RE_TOTAL_SECAO = re.compile(r"^(?:Total|Subtotal)\b")
# Linhas de dado (detalhe de ligação): "08/06 12:41:16 São Paulo ..."
_RE_LINHA_DADO = re.compile(r"^\d{2}/\d{2}\s+\d{2}:\d{2}")
# Rodapé de página e cabeçalhos de coluna — nunca são título de seção.
_RE_RODAPE = re.compile(r"^(?:P\w+g\.\s*\d+|\d{11}-\d\s)")
_CABECALHOS_COLUNA = ("Data Hora", "Serviço Mbytes", "Descrição Total", "Valor Cobrado")

_MESES_INICIO_SECAO = "Mensalidades e Pacotes Promocionais"

# Resumo da pág. 1: "1. Plano Contratado R$ 2.202,70" (o nº da categoria varia).
_RE_CATEGORIA = re.compile(r"^\d+\.\s+(?P<descricao>.+?)\s+R\$\s*(?P<valor>-?[\d.]+,\d{2})\s*$")
# Detalhe dos lançamentos de conta: "3. OUTROS LANÇAMENTOS VALOR R$" ... "SUBTOTAL - ...".
# O sufixo "VALOR R$" é obrigatório: sem ele o padrão casaria também com a linha
# do RESUMO ("3. Outros Lançamentos R$ -9,02") e varreria a página inteira.
_RE_OUTROS_INICIO = re.compile(r"^\d+\.\s+OUTROS LAN\w+AMENTOS\s+VALOR\s+R\$", re.IGNORECASE)
_RE_OUTROS_FIM = re.compile(r"^SUBTOTAL\s*-\s*OUTROS LAN\w+AMENTOS", re.IGNORECASE)
# Item dentro dela: "Desconto Créditos Anteriores -9,02".
_RE_ITEM_AJUSTE = re.compile(r"^(?P<descricao>.+?)\s+(?P<valor>-?\d{1,3}(?:\.\d{3})*,\d{2})$")


# ---------------------------------------------------------------------------
# Helpers de conversão
# ---------------------------------------------------------------------------
def _para_decimal(texto: str) -> Decimal:
    """'1.640,58' -> Decimal('1640.58'). Levanta BoletoInvalido se não converter."""
    try:
        return Decimal(texto.strip().replace(".", "").replace(",", "."))
    except InvalidOperation as exc:
        raise BoletoInvalido(f"Valor monetário ilegível: '{texto}'.") from exc


def _para_data(texto: str | None) -> date | None:
    """'20/07/2026' -> date. Devolve None quando ausente/ilegível."""
    if not texto:
        return None
    try:
        return datetime.strptime(texto.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _buscar(padrao: str, texto: str, flags: int = 0) -> str:
    """Primeiro grupo capturado de `padrao` em `texto`, ou '' se não casar."""
    achado = re.search(padrao, texto, flags)
    return achado.group(1).strip() if achado else ""


def _digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def _extrair_texto(conteudo: bytes) -> list[str]:
    """Texto do PDF como uma lista única de linhas (páginas concatenadas)."""
    try:
        leitor = PdfReader(BytesIO(conteudo))
        paginas = [pagina.extract_text() or "" for pagina in leitor.pages]
    except Exception as exc:  # noqa: BLE001 — pypdf levanta tipos variados
        raise BoletoInvalido(f"Não foi possível ler o PDF: {exc}") from exc
    linhas = "\n".join(paginas).split("\n")
    return [l.strip() for l in linhas]


# ---------------------------------------------------------------------------
# Cabeçalho
# ---------------------------------------------------------------------------
def _ler_categorias(linhas: list[str]) -> list[CategoriaBoleto]:
    """
    Lê o resumo "Veja aqui o que está sendo cobrado" da pág. 1.

    Para em "Total a pagar": o mesmo padrão numerado reaparece adiante como
    título das seções detalhadas ("1. PLANO CONTRATADO VALOR R$").
    """
    categorias: list[CategoriaBoleto] = []
    for texto in linhas:
        if texto.startswith("Total a pagar"):
            break
        casado = _RE_CATEGORIA.match(texto)
        if casado:
            categorias.append(
                CategoriaBoleto(
                    descricao=casado.group("descricao").strip(),
                    valor=_para_decimal(casado.group("valor")),
                )
            )
    return categorias


def _ler_ajustes(linhas: list[str]) -> list[AjusteBoleto]:
    """
    Lê TODOS os itens da seção "Outros Lançamentos" (se houver).

    Nada é reconhecido por nome: o que estiver listado ali vira um ajuste, com a
    descrição que a operadora deu. Boletos sem a seção devolvem lista vazia.
    """
    ajustes: list[AjusteBoleto] = []
    dentro = False
    for texto in linhas:
        if not dentro:
            if _RE_OUTROS_INICIO.match(texto):
                dentro = True
            continue
        if _RE_OUTROS_FIM.match(texto):
            break
        item = _RE_ITEM_AJUSTE.match(texto)
        if item:
            ajustes.append(
                AjusteBoleto(
                    descricao=item.group("descricao").strip(),
                    valor=_para_decimal(item.group("valor")),
                )
            )
    return ajustes


def _ler_cabecalho(boleto: BoletoClaro, linhas: list[str]) -> None:
    """Preenche os campos de cabeçalho a partir do texto completo do PDF."""
    texto = "\n".join(linhas)

    # A 1ª linha não vazia da pág. 1 é a razão social do tomador.
    boleto.razao_social = next((l for l in linhas if l), "")

    # Resumo da conta (pág. 1). O PDF usa um caractere corrompido em "Nº",
    # então casamos apenas pelo sufixo ("da conta:" / "do cliente:").
    boleto.conta = _buscar(r"da conta:\s*(\d+)", texto)
    boleto.cliente = _buscar(r"do cliente:\s*(\d+)", texto)
    boleto.cnpj_tomador = _buscar(r"CPF/CNPJ\s+([\d.]{10,}/[\d-]+)", texto)
    boleto.vencimento = _para_data(_buscar(r"Vencimento\s*\n?(\d{2}/\d{2}/\d{4})", texto))
    boleto.periodo_inicio = _para_data(_buscar(r"de (\d{2}/\d{2}/\d{4}) a \d{2}/\d{2}/\d{4}", texto))
    boleto.periodo_fim = _para_data(_buscar(r"de \d{2}/\d{2}/\d{4} a (\d{2}/\d{2}/\d{4})", texto))
    boleto.linha_digitavel = _buscar(r"(\d{11}-\d \d{11}-\d \d{11}-\d \d{11}-\d)", texto)

    total = _buscar(r"Total a pagar R\$\s*(-?[\d.]+,\d{2})", texto)
    boleto.valor_total = _para_decimal(total) if total else None

    # DANFE-COM / NFCOM (pág. 3). O boleto não gera pré-nota, mas o dep. fiscal
    # precisa desses dados no lançamento.
    boleto.competencia = _buscar(r"Refer\w+ncia\s*\n(\d{2}/\d{4})", texto)
    boleto.nfcom_numero = _buscar(r"NFCOM N.\s*(\d+)", texto)
    boleto.nfcom_serie = _buscar(r"S\w+RIE\s+(\d+)", texto)
    boleto.nfcom_chave = _digitos(_buscar(r"Chave de acesso:\s*\n([\d ]+)", texto))
    boleto.emissao = _para_data(_buscar(r"DATA DE EMISS\w+O\s+(\d{2}/\d{2}/\d{4})", texto))

    # Lançamentos de conta e a decomposição declarada (esta só para diagnóstico).
    boleto.categorias = _ler_categorias(linhas)
    boleto.ajustes = _ler_ajustes(linhas)


# ---------------------------------------------------------------------------
# Blocos de detalhamento (uma linha telefônica cada)
# ---------------------------------------------------------------------------
def _e_titulo_secao(linha: str) -> bool:
    """True para linhas que nomeiam uma seção de uso (ex.: 'Ligações Locais')."""
    if not linha or len(linha) < 4:
        return False
    if _RE_LINHA_DADO.match(linha) or _RE_TOTAL_SECAO.match(linha):
        return False
    if linha.startswith("TOTAL") or _RE_RODAPE.match(linha):
        return False
    if any(c in linha for c in _CABECALHOS_COLUNA):
        return False
    # Título não carrega valor; linhas com moeda ao final são item/dado.
    return not _RE_MOEDA.search(linha)


def _ler_bloco(numero_exibicao: str, corpo: list[str]) -> LinhaBoleto:
    """
    Lê um bloco de detalhamento e devolve a linha com sua composição de valor.

    Percorre o bloco em dois regimes: dentro de "Mensalidades e Pacotes
    Promocionais" cada linha é um item; fora dele, só interessam os fechamentos
    de seção ("Total"/"Subtotal"), cuja última coluna é o valor cobrado.
    """
    linha = LinhaBoleto(numero=_digitos(numero_exibicao), numero_exibicao=numero_exibicao)
    em_mensalidades = False
    secao_atual = ""

    for texto in corpo:
        if not texto:
            continue

        if texto.startswith(_MESES_INICIO_SECAO):
            em_mensalidades = True
            continue

        if em_mensalidades:
            fim = _RE_TOTAL_MENSALIDADES.match(texto)
            if fim:
                # O "TOTAL R$" é conferência do que já somamos item a item.
                em_mensalidades = False
                continue
            if texto.startswith("Descrição"):  # cabeçalho de coluna
                continue
            item = _RE_ITEM_MENSALIDADE.match(texto)
            if item:
                linha.servicos.append(
                    ServicoLinha(
                        descricao=item.group("descricao").strip(),
                        categoria=CATEGORIA_MENSALIDADE,
                        valor=_para_decimal(item.group("valor")),
                    )
                )
            continue

        # Fora das mensalidades: seções de uso.
        if _RE_TOTAL_SECAO.match(texto):
            valores = _RE_MOEDA.findall(texto)
            if not valores:
                continue
            # A última coluna do fechamento é sempre o "Valor Cobrado".
            cobrado = _para_decimal(valores[-1])
            if cobrado != 0:
                linha.servicos.append(
                    ServicoLinha(
                        descricao=secao_atual or "Serviços utilizados",
                        categoria=CATEGORIA_USO,
                        valor=cobrado,
                    )
                )
            continue

        if _e_titulo_secao(texto):
            secao_atual = texto

    return linha


def _fundir(destino: LinhaBoleto, origem: LinhaBoleto) -> None:
    """Acumula a composição de um bloco de continuação na linha já lida."""
    destino.servicos.extend(origem.servicos)


def ler_boleto(nome_arquivo: str, conteudo: bytes) -> BoletoClaro:
    """
    Lê um PDF de boleto da Claro.

    Args:
        nome_arquivo: nome do upload (fica no resultado, para o usuário
                      identificar de qual boleto veio cada lançamento).
        conteudo: bytes do PDF.

    Returns:
        BoletoClaro com cabeçalho e linhas. A conferência do total NÃO é feita
        aqui — quem decide o que fazer com `confere`/`diferenca` é o módulo.

    Raises:
        BoletoInvalido: PDF ilegível ou sem nenhum bloco de detalhamento.
    """
    linhas_texto = _extrair_texto(conteudo)
    boleto = BoletoClaro(nome_arquivo=nome_arquivo)
    _ler_cabecalho(boleto, linhas_texto)

    # Índices de início de cada bloco de detalhamento.
    # A segunda compreensão descarta os `None`; a lista tipada explicita isso
    # (reatribuir a mesma variável mantinha o tipo opcional).
    inicios: list[tuple[int, re.Match[str]]] = [
        (i, m) for i, l in enumerate(linhas_texto) if (m := _RE_BLOCO.match(l))
    ]
    if not inicios:
        raise BoletoInvalido(
            f"'{nome_arquivo}' não parece um boleto da Claro: nenhum detalhamento "
            "de celular foi encontrado no PDF."
        )

    por_numero: dict[str, LinhaBoleto] = {}
    for posicao, (indice, casado) in enumerate(inicios):
        fim = inicios[posicao + 1][0] if posicao + 1 < len(inicios) else len(linhas_texto)
        ddd, numero = casado.group(1), casado.group(2)
        exibicao = f"({ddd}) {numero}"
        lida = _ler_bloco(exibicao, linhas_texto[indice + 1 : fim])
        if lida.numero in por_numero:
            _fundir(por_numero[lida.numero], lida)  # bloco de continuação
        else:
            por_numero[lida.numero] = lida

    boleto.linhas = list(por_numero.values())
    return boleto
