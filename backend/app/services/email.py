"""
Envio de e-mail (SMTP) — genérico e reutilizável por qualquer rateio/notificação.

Não sabe nada de Unimed/pré-nota/fiscal: recebe destinatários, assunto, corpo e
anexos, e envia via SMTP configurado no `.env`. O CONTEÚDO (o que vai no e-mail)
é responsabilidade de cada compositor (ex.: services/notificacao.py).
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any, cast

from app.config import Settings


class EmailError(Exception):
    """Falha de configuração ou de envio de e-mail."""


def enviar_email(
    settings: Settings,
    destinatarios: list[str],
    assunto: str,
    corpo: str,
    anexos: list[dict[str, Any]] | None = None,
    corpo_html: str | None = None,
    imagens_inline: list[dict[str, Any]] | None = None,
    copia: list[str] | None = None,
    responder_para: list[str] | None = None,
) -> None:
    """
    Envia um e-mail com anexos opcionais.

    Com `corpo_html`, envia multipart/alternative: o HTML é a versão exibida e o
    texto fica como alternativa (clientes que bloqueiam HTML, leitores de tela e
    filtros continuam lendo o conteúdo). `anexos`: lista de {nome, conteudo
    (bytes), mime}. `imagens_inline`: lista de {cid, conteudo (bytes), mime} —
    imagens do layout, referenciadas no HTML como `cid:<cid>`, que não contam como
    anexo. `copia` vai em Cc (visível: quem recebeu precisa saber quem mais
    recebeu) e `responder_para` em Reply-To, para a resposta cair em quem tratou
    o rateio, e não no remetente técnico da ferramenta. Lança EmailError em falha
    de configuração ou de envio.
    """
    if not settings.smtp_host:
        raise EmailError("SMTP não configurado — defina SMTP_HOST no .env.")
    if not destinatarios:
        raise EmailError("Nenhum destinatário — defina FISCAL_EMAILS no .env.")

    remetente = settings.smtp_from or settings.smtp_user
    if not remetente:
        raise EmailError("Remetente não configurado — defina SMTP_FROM ou SMTP_USER.")

    # Cópia não pode repetir quem já está no Para (o destinatário receberia duas
    # vezes) nem entrar vazia (cabeçalho Cc em branco é recusado por alguns MTAs).
    copia = [e for e in dict.fromkeys(copia or []) if e not in destinatarios]

    msg = EmailMessage()
    msg["From"] = remetente
    msg["To"] = ", ".join(destinatarios)
    if copia:
        msg["Cc"] = ", ".join(copia)
    if responder_para:
        msg["Reply-To"] = ", ".join(dict.fromkeys(responder_para))
    msg["Subject"] = assunto
    msg.set_content(corpo)
    if corpo_html:
        msg.add_alternative(corpo_html, subtype="html")
        # Imagens do layout (logo) vão EMBUTIDAS, referenciadas por cid: no HTML.
        # É o único jeito confiável: Outlook e Gmail bloqueiam imagem externa por
        # padrão e descartam data URI, então a logo simplesmente não apareceria.
        # `add_related` na parte HTML monta multipart/related — a imagem fica
        # ligada ao corpo e NÃO aparece na lista de anexos do e-mail.
        # `get_payload()` é tipado como str | list | Message; aqui, depois de
        # `add_alternative`, é sempre a lista de partes e a última é o HTML.
        partes = msg.get_payload()
        assert isinstance(partes, list)
        parte_html = cast(EmailMessage, partes[-1])
        for imagem in imagens_inline or []:
            mime_img = (imagem.get("mime") or "image/png").strip()
            principal, _, sub = mime_img.partition("/")
            parte_html.add_related(
                imagem["conteudo"],
                maintype=principal or "image",
                subtype=sub or "png",
                cid=f"<{imagem['cid']}>",
            )

    for anexo in anexos or []:
        mime = (anexo.get("mime") or "application/octet-stream").strip()
        maintype, _, subtype = mime.partition("/")
        msg.add_attachment(
            anexo["conteudo"],
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=anexo.get("nome") or "anexo",
        )

    # `send_message` deriva os envelopes de To + Cc, então a cópia é entregue
    # sem precisar montar a lista de destinatários à mão.
    try:
        if settings.smtp_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as s:
                if settings.smtp_user:
                    s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
                if settings.smtp_tls:
                    s.starttls()
                if settings.smtp_user:
                    s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailError(f"Falha ao enviar e-mail: {type(exc).__name__}: {exc}") from exc
