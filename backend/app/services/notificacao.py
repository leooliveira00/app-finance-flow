"""
Compositores de notificação ao dep. fiscal (conteúdo do e-mail por rateio).

Reaproveita o sender genérico (services/email.py). Aqui mora só o CONTEÚDO: a
partir de uma `Execucao` (com títulos por empresa + reconciliação com nº/valor/
vencimento da NF + documentos), monta assunto, corpo e anexos. Cada novo rateio
que precisar notificar adiciona seu compositor e `montar_notificacao` despacha.
"""

from __future__ import annotations

import html
import pathlib
import re
import unicodedata
from decimal import Decimal
from functools import lru_cache
from string import Template
from typing import Any

from app.config import Settings
from app.models.execucao import Execucao
from app.services.organizacao_fiscal import ConfigFiscal

_OPERADORA_LABEL = {"unimed": "Unimed Nacional", "bradesco": "Bradesco Saúde"}

# Assinatura: identifica a origem em toda notificação (pedido do dep. fiscal).
ASSINATURA = (
    "Este rateio e seus títulos foram processados pela ferramenta FinanceFlow. "
    "Em caso de dúvidas, procure a área responsável pelo processo."
)


def _esc(valor: Any) -> str:
    """Escapa o texto para interpolação segura no HTML do e-mail."""
    return html.escape(str(valor if valor is not None else ""), quote=True)


def _norm(v: Any) -> str:
    forma = unicodedata.normalize("NFKD", str(v or "")).upper()
    return "".join(c for c in forma if not unicodedata.combining(c)).strip()


def _moeda(valor: Any) -> str:
    d = Decimal(str(valor or 0))
    s = f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _competencia(comp: str) -> str:
    return f"{comp[4:]}/{comp[:4]}" if comp and len(comp) == 6 else (comp or "—")


def _processo(id_: int | None) -> str:
    """Nº do processo (id da execução) para rastreio, zero-padded (ex.: 023)."""
    return str(id_ or 0).zfill(3)


def _empresas_do_envio(cfg: ConfigFiscal, execucao: Execucao) -> list[dict[str, str]]:
    """Uma linha por empresa integrada: NF, valor, vencimento e o que foi gerado."""
    resultado = execucao.resultado or {}
    recon = {_norm(r.get("empresa")): r for r in resultado.get("reconciliacao", [])}
    itens: list[dict[str, str]] = []
    for envio in execucao.envios:
        if envio.status != "enviado":
            continue
        r = recon.get(_norm(envio.empresa)) or {}
        itens.append({
            "empresa": str(r.get("empresa") or envio.empresa),
            "nf": str(r.get("numero_documento") or "—"),
            "valor": _moeda(r.get("valor_documento")),
            "vencimento": str(r.get("vencimento_documento") or "—"),
            # Rótulo e valor separados: o valor entra em negrito na mesma
            # tabela de NF/valor/vencimento, em vez de uma frase solta embaixo.
            **(
                {"lancamento_rotulo": "Lançamento", "lancamento_valor": "Pré-nota (entrada da NF)"}
                if cfg.rotina_erp(envio.empresa) == "pre_nota"
                else {"lancamento_rotulo": "Autorização de entrega", "lancamento_valor": envio.titulo or "—"}
            ),
        })
    return itens


def _corpo_texto(empresas: list[dict[str, str]], label: str) -> str:
    """Versão texto (alternativa do multipart) — mesmo conteúdo do HTML."""
    linhas = [f"Segue anexo NF e boleto da empresa {label}:", ""]
    for e in empresas:
        linhas += [
            e["empresa"],
            f"NF: {e['nf']}",
            f"Valor: {e['valor']}",
            f"Vencimento: {e['vencimento']}",
            f"{e['lancamento_rotulo']}: {e['lancamento_valor']}",
            "",
        ]
    linhas += ["—", ASSINATURA]
    return "\n".join(linhas).strip()


TEMPLATES = pathlib.Path(__file__).resolve().parent.parent / "templates" / "email"
# Logo do cabeçalho: versão reduzida (240x136) da usada na sidebar, com fundo
# transparente — o cabeçalho do e-mail é navy, como a sidebar. Vai EMBUTIDA no
# corpo (cid), não como anexo: e-mail com imagem externa aparece sem a logo.
ARQUIVO_LOGO = "logo-financeflow.png"
CID_LOGO = "logo"


@lru_cache(maxsize=1)
def _logo() -> bytes | None:
    """Bytes da logo do e-mail; None se o arquivo não estiver presente."""
    caminho = TEMPLATES / ARQUIVO_LOGO
    return caminho.read_bytes() if caminho.is_file() else None


# Comentários HTML do template: removidos ANTES da substituição. Sem isto, um
# placeholder citado num comentário (ex.: documentando os campos) recebe valor e
# o conteúdo aparece DUAS vezes no e-mail — e o resto do comentário vaza como
# texto para o leitor.
_RE_COMENTARIO_HTML = re.compile(r"<!--.*?-->", re.DOTALL)


@lru_cache(maxsize=8)
def _template(nome: str) -> Template:
    """Template de e-mail lido de `app/templates/email` (cacheado por processo).

    Arquivo separado de propósito: ajustar o visual do e-mail (cores, ordem dos
    campos, texto) não deveria exigir mexer em Python. `string.Template` usa $var,
    então chaves de CSS no arquivo não conflitam com a interpolação.
    """
    bruto = (TEMPLATES / nome).read_text(encoding="utf-8")
    return Template(_RE_COMENTARIO_HTML.sub("", bruto))


def montar_html(
    *, subtitulo: str, intro: str, conteudo: str, area: str, processo: str
) -> str:
    """
    Esqueleto de e-mail da plataforma (cabeçalho com logo, intro, corpo, rodapé).

    REAPROVEITÁVEL por qualquer processo que notifique por e-mail: quem chama
    monta só o `conteudo` (blocos próprios) e recebe a identidade visual, a
    assinatura e o rodapé de rastreio (processo + área) já resolvidos. `conteudo`
    entra como HTML — quem monta é responsável por escapar os valores.
    """
    return _template("notificacao_fiscal.html").safe_substitute(
        subtitulo=_esc(subtitulo),
        intro=_esc(intro),
        conteudo=conteudo,
        area=_esc(area),
        processo=_esc(processo),
        assinatura=_esc(ASSINATURA),
    )


def _corpo_html(
    empresas: list[dict[str, str]], label: str, area: str, competencia: str, processo: str,
) -> str:
    """Monta o HTML da notificação a partir dos templates (valores escapados).

    Template ÚNICO: o mesmo e-mail sai em teste e em produção, para o que o fiscal
    recebe poder ser analisado tal como será. A distinção de ambiente fica no
    assunto (prefixo) e na auditoria da execução, não no corpo.
    """
    bloco_empresa = _template("notificacao_fiscal_empresa.html")
    conteudo = "".join(
        bloco_empresa.safe_substitute(
            empresa=_esc(e["empresa"]), nf=_esc(e["nf"]), valor=_esc(e["valor"]),
            vencimento=_esc(e["vencimento"]),
            lancamento_rotulo=_esc(e["lancamento_rotulo"]),
            lancamento_valor=_esc(e["lancamento_valor"]),
        )
        for e in empresas
    )
    return montar_html(
        subtitulo=f"{area} · {label} · competência {competencia}",
        intro="Seguem em anexo a nota fiscal e o boleto, com os títulos gerados no ERP.",
        conteudo=conteudo,
        area=area,
        processo=processo,
    )


def _montar_pagamento(
    settings: Settings, cfg: ConfigFiscal, execucao: Execucao, area: str = ""
) -> dict[str, Any]:
    operadora = "bradesco" if "bradesco" in execucao.tipo else "unimed"
    label = _OPERADORA_LABEL.get(operadora, operadora.title())
    empresas = _empresas_do_envio(cfg, execucao)
    competencia = _competencia(execucao.competencia)
    processo = _processo(execucao.id)
    area = (area or "").strip() or "—"
    # Enquanto os títulos são gravados fora da base oficial, o assunto avisa: o
    # fiscal não pode tratar um título de teste como real.
    teste = not settings.escrita_em_producao

    anexos = [
        {"nome": d.nome, "conteudo": d.conteudo, "mime": d.mime or "application/octet-stream"}
        for d in execucao.documentos
        if d.categoria in ("nf", "boleto")
    ]
    # Área na frente: o fiscal recebe de vários processos e filtra/prioriza por ela.
    assunto = (
        f"{'[TESTE] ' if teste else ''}{area} - Rateio {label} — competência {competencia} "
        f"(NF e boleto) - Processo: {processo}"
    )
    logo = _logo()
    return {
        "assunto": assunto,
        "corpo": _corpo_texto(empresas, label),
        "corpo_html": _corpo_html(empresas, label, area, competencia, processo),
        "anexos": anexos,
        # Sem o arquivo, o HTML mostra o alt ("Vertex") e o e-mail sai normal.
        "imagens_inline": (
            [{"cid": CID_LOGO, "conteudo": logo, "mime": "image/png"}] if logo else []
        ),
    }


def _montar_telefonia(
    settings: Settings, cfg: ConfigFiscal, execucao: Execucao, area: str = ""
) -> dict[str, Any]:
    """
    Notificação da telefonia: um bloco por BOLETO lançado, num envio só.

    A quantidade de boletos é livre (1, 2 ou N) e cada um gerou um título. O
    identificador que amarra título e boleto é a CONTA da Claro — a mesma que vai
    na observação do lançamento no ERP.
    """
    from app.modules.registry import registry  # import tardio evita ciclo

    # Competência/valor vêm do que o MÓDULO declarou como título (mesma fonte do
    # envio); o número do título vem do que o ERP devolveu, por referência.
    modulo = registry.get(execucao.tipo)
    por_referencia = {
        # Capacidade opcional: quem chega aqui já passou pelo hasattr do router;
        # declará-la no `RateioModule` faria TODO módulo parecer tê-la.
        str(t["referencia"]): t
        for t in modulo.titulos_erp(execucao.resultado or {})  # type: ignore[attr-defined]
    }
    lancados = [
        {
            "titulo": envio.titulo or "—",
            "conta": envio.referencia or "—",
            "competencia": _competencia(
                str((por_referencia.get(envio.referencia or "") or {}).get("competencia", ""))
            ),
            "valor": _moeda((por_referencia.get(envio.referencia or "") or {}).get("valor")),
        }
        for envio in execucao.envios
        if envio.status == "enviado"
    ]
    lancados.sort(key=lambda t: t["conta"])

    bloco = _template("notificacao_telefonia_titulo.html")
    conteudo = "".join(
        bloco.safe_substitute(
            titulo=_esc(t["titulo"]), conta=_esc(t["conta"]),
            competencia=_esc(t["competencia"]), valor=_esc(t["valor"]),
        )
        for t in lancados
    )

    competencia = _competencia(execucao.competencia)
    processo = _processo(execucao.id)
    area = (area or "").strip() or "—"
    quantos = len(lancados)
    intro = (
        f"Seguem em anexo {quantos} boleto(s) da Claro, com os títulos gerados no ERP."
    )

    linhas = [intro, ""]
    for t in lancados:
        linhas += [
            f"Título: {t['titulo']} - Conta: {t['conta']}",
            f"Competência: {t['competencia']}",
            f"Valor: {t['valor']}",
            "",
        ]
    linhas += ["—", ASSINATURA]

    anexos = [
        {"nome": d.nome, "conteudo": d.conteudo, "mime": d.mime or "application/octet-stream"}
        for d in execucao.documentos
        if d.categoria == "boleto"
    ]
    teste = not settings.escrita_em_producao
    assunto = (
        f"{'[TESTE] ' if teste else ''}{area} - Telefonia Claro — competência {competencia} "
        f"({quantos} boleto(s)) - Processo: {processo}"
    )
    logo = _logo()
    return {
        "assunto": assunto,
        "corpo": "\n".join(linhas).strip(),
        "corpo_html": montar_html(
            subtitulo=f"{area} · Telefonia Claro · competência {competencia}",
            intro=intro,
            conteudo=conteudo,
            area=area,
            processo=processo,
        ),
        "anexos": anexos,
        "imagens_inline": (
            [{"cid": CID_LOGO, "conteudo": logo, "mime": "image/png"}] if logo else []
        ),
    }


def montar_notificacao(
    settings: Settings, cfg: ConfigFiscal, execucao: Execucao, area: str = ""
) -> dict[str, Any]:
    """Monta a notificação ao fiscal para rateios que a suportam.

    O rateio precisa declarar `notifica_fiscal = True` (capacidade do módulo);
    hoje só os pagamentos de plano de saúde usam o formato `_montar_pagamento`.
    `area` (a do processo) vem do router — identifica a origem no assunto e no
    rodapé, porque o fiscal recebe notificações de áreas diferentes.
    Devolve {assunto, corpo, corpo_html, anexos}.
    """
    from app.modules.registry import registry  # import tardio evita ciclo

    try:
        notifica = bool(getattr(registry.get(execucao.tipo), "notifica_fiscal", False))
    except KeyError:
        notifica = False
    if notifica:
        # Um título por documento (telefonia) tem formato próprio: bloco por
        # boleto com título + conta, e nenhuma NF envolvida.
        try:
            por_documento = hasattr(registry.get(execucao.tipo), "titulos_erp")
        except KeyError:
            por_documento = False
        if por_documento:
            return _montar_telefonia(settings, cfg, execucao, area)
        return _montar_pagamento(settings, cfg, execucao, area)
    raise ValueError(f"Notificação ao fiscal não configurada para o rateio '{execucao.tipo}'.")
