"""
Execuções de rateio confirmadas: persistência + envio ao ERP + histórico.

- POST   /api/execucoes                         confirma (grava snapshot + documentos)
- GET    /api/execucoes                          histórico (filtrado por área)
- GET    /api/execucoes/{id}                      detalhe (snapshot + envios + docs)
- GET    /api/execucoes/{id}/documentos/{doc_id}  download de um documento
- POST   /api/execucoes/{id}/enviar               envia ao ERP (idempotente; reenvio)

O envio ao ERP (Autorização de Entrega sobre Contrato de Parceria) roda em
`services.erp`; aqui só orquestramos a persistência do resultado por empresa.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import service as auth_service
from app.auth.deps import usuario_atual
from app.auth.redacao import redigir_resultado
from app.config import Settings, get_settings
from app.db.session import get_db
from app.models.execucao import Documento, EnvioErp, EnvioTentativa, Execucao
from app.modules._plano_saude import validators as ps_validators
from app.modules.registry import registry
from app.services import (
    email,
    erp,
    notificacao,
    notificacao_config,
    organizacao,
    organizacao_fiscal,
)


def _tem_capacidade(tipo: str, capacidade: str) -> bool:
    """Consulta uma capacidade do módulo (ex.: 'lanca_no_erp') sem farejar o nome
    do tipo. Módulo ausente (ex.: rateio removido) -> capacidade False."""
    try:
        return bool(getattr(registry.get(tipo), capacidade, False))
    except KeyError:
        return False

router = APIRouter(prefix="/execucoes", tags=["execucoes"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _exigir_acesso(usuario: dict, tipo: str, db: Session) -> None:
    area_map = organizacao.mapa_areas_rateios(db)
    if not auth_service.pode_ver(usuario["areas"], tipo, area_map):
        raise HTTPException(status_code=403, detail=f"Sem permissão para o rateio '{tipo}'.")


def _categoria(tipo: str, nome: str, conteudo: bytes = b"") -> str:
    n = (nome or "").lower()
    if n.endswith((".xlsx", ".xls")):
        return "planilha"
    if n.endswith(".pdf"):
        # Classifica pelo CONTEÚDO do PDF (NF vs boleto, qualquer operadora/banco),
        # não pelo tipo do rateio — assim NF e boleto enviados juntos recebem o
        # rótulo correto. Fallback por tipo quando o PDF não é reconhecido/ilegível.
        if conteudo:
            try:
                tipo_doc = ps_validators.classificar_pdf(nome, conteudo)
            except Exception:  # noqa: BLE001 — PDF corrompido/inesperado vira fallback
                tipo_doc = None
            if tipo_doc:
                return tipo_doc
        return "boleto" if "bradesco" in tipo else "nf"
    return "outro"


def _calc_total(resultado: dict) -> Decimal:
    """Total do rateio a partir do snapshot (pagamento: rateado+estornos; copart: total_descontado)."""
    totais = resultado.get("totais")
    if isinstance(totais, list) and totais:
        return sum(
            (Decimal(str(t.get("rateado", 0))) + Decimal(str(t.get("estornos", 0))) for t in totais),
            Decimal("0"),
        )
    if resultado.get("total_descontado") is not None:
        return Decimal(str(resultado["total_descontado"]))
    agregado = resultado.get("agregado") or []
    return sum((Decimal(str(a.get("valor", 0))) for a in agregado), Decimal("0"))


def _envio_dict(e: EnvioErp) -> dict:
    return {
        "empresa": e.empresa, "referencia": e.referencia, "rest": e.rest,
        "contrato": e.contrato,
        "titulo": e.titulo, "status": e.status, "mensagem": e.mensagem,
        "erp_ambiente": e.erp_ambiente, "erp_base_url": e.erp_base_url,
        "enviados": e.enviados, "aceitos": e.aceitos,
        "matriculas_pendentes": e.matriculas_pendentes or [],
    }


def _tentativa_dict(t: EnvioTentativa) -> dict:
    return {
        "id": t.id, "empresa": t.empresa, "referencia": t.referencia,
        "rest": t.rest, "contrato": t.contrato,
        "titulo": t.titulo, "status": t.status, "mensagem": t.mensagem,
        "usuario": t.usuario,
        "erp_ambiente": t.erp_ambiente, "erp_base_url": t.erp_base_url,
        # Só nas falhas: é onde o corpo bruto tem valor de diagnóstico.
        "resposta_erp": t.resposta_erp if t.status != "enviado" else None,
        "criado_em": t.criado_em.isoformat() if t.criado_em else None,
    }


def _execucao_dict(e: Execucao, incluir_resultado: bool = False) -> dict:
    d: dict[str, Any] = {
        "id": e.id,
        "tipo": e.tipo,
        "competencia": e.competencia,
        "usuario": e.usuario,
        "criado_em": e.criado_em.isoformat() if e.criado_em else None,
        "notificado_em": e.notificado_em.isoformat() if e.notificado_em else None,
        # A quem a notificação foi enviada ({para, copia}); vazio nas execuções
        # anteriores a este registro.
        "notificado_para": e.notificado_para or None,
        "status": e.status,
        "total": str(e.total),
        "documentos": [
            {"id": d.id, "categoria": d.categoria, "nome": d.nome, "mime": d.mime}
            for d in e.documentos
        ],
        "envios": [_envio_dict(x) for x in e.envios],
        # Histórico de tentativas (append-only), em ordem cronológica (mais antiga primeiro).
        "tentativas": [
            _tentativa_dict(t) for t in sorted(e.tentativas, key=lambda x: x.id)
        ],
    }
    if incluir_resultado:
        d["resultado"] = e.resultado
    return d


def _matriculas(pendentes: Any) -> list[str]:
    """Matrículas de `matriculas_pendentes`, que guarda objetos {matricula, nome, motivo}.

    Aceita também lista de strings: é o formato que a coluna teve na primeira
    versão, e um reenvio de execução gravada antes não pode quebrar.
    """
    saida: list[str] = []
    for p in pendentes or []:
        if isinstance(p, dict):
            mat = str(p.get("matricula") or "").strip()
        else:
            mat = str(p or "").strip()
        if mat:
            saida.append(mat)
    return saida


def _elegivel_erp(tipo: str, item: dict) -> bool:
    """Delega ao módulo a regra de quem entra no lançamento (capacidade opcional).

    Sem `elegivel_erp` no módulo, cai no critério genérico: tem empresa e valor.
    """
    try:
        modulo = registry.get(tipo)
    except KeyError:
        modulo = None
    regra = getattr(modulo, "elegivel_erp", None)
    if regra is not None:
        return bool(regra(item))
    return Decimal(str(item.get("valor_descontado", "0") or "0")) != 0


def _unidades_do_snapshot(tipo: str, resultado: dict) -> set[str]:
    """
    Unidades que precisam ser lançadas para a execução fechar como "enviado".

    Rateio que declara `titulos_erp` (um título por documento) tem uma unidade por
    documento — a empresa sozinha não serve, senão o primeiro boleto lançado já
    fecharia a execução com os outros pendentes.
    """
    try:
        modulo = registry.get(tipo)
    except KeyError:
        modulo = None
    titulos = getattr(modulo, "titulos_erp", None)
    if titulos is not None:
        empresa = get_settings().protheus_claro_empresa.strip().upper()
        return {f"{empresa}|{t['referencia']}" for t in titulos(resultado)}
    return _empresas_do_snapshot(tipo, resultado)


def _empresas_do_snapshot(tipo: str, resultado: dict) -> set[str]:
    """
    Empresas que PRECISAM ser enviadas ao ERP, em MAIÚSCULAS.

    Dois formatos de snapshot: pagamento traz `agregado` (por CC/classe) e
    coparticipação traz `itens` (por colaborador × operadora). Sem este fallback a
    coparticipação nunca fecharia como "enviado" (o conjunto sairia vazio).

    Usa o MESMO critério de elegibilidade do lote (PJ, teto atingido, sem
    matrícula e valor zerado ficam fora): se divergisse, uma empresa cujos
    colaboradores estão todos em tratativa manual ficaria eternamente pendente.
    """
    empresas = {
        str(a.get("empresa", "")).strip().upper()
        for a in resultado.get("agregado") or []
        if Decimal(str(a.get("valor", "0") or "0")) != 0
    }
    if empresas:
        return empresas
    return {
        str(i.get("empresa", "")).strip().upper()
        for i in resultado.get("itens") or []
        if _elegivel_erp(tipo, i)
    } - {""}


def _status_execucao(envios: list[EnvioErp]) -> str:
    st = [e.status for e in envios]
    if st and all(s == "enviado" for s in st):
        return "enviado"
    if any(s == "erro" for s in st):
        return "erro_envio"
    if any(s == "parcial" for s in st):
        return "parcial"
    return "pendente_envio"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("", status_code=status.HTTP_201_CREATED)
async def confirmar(
    tipo: str = Form(...),
    competencia: str = Form(""),
    resultado: str = Form(...),
    arquivos: list[UploadFile] = File(default=[]),
    usuario: dict = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> dict:
    """Grava a execução confirmada (snapshot do resultado + documentos)."""
    _exigir_acesso(usuario, tipo, db)
    try:
        snap = json.loads(resultado)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Resultado inválido (JSON).") from exc

    execucao = Execucao(
        tipo=tipo,
        competencia=competencia,
        usuario=usuario.get("email", ""),
        status="pendente_envio",
        total=_calc_total(snap),
        resultado=snap,
    )
    db.add(execucao)
    for f in arquivos:
        conteudo = await f.read()
        execucao.documentos.append(
            Documento(
                categoria=_categoria(tipo, f.filename or "", conteudo),
                nome=f.filename or "arquivo",
                mime=f.content_type or "",
                conteudo=conteudo,
            )
        )
    db.commit()
    db.refresh(execucao)
    return _execucao_dict(execucao)


@router.get("")
def listar(
    usuario: dict = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> list[dict]:
    permitidos = auth_service.tipos_permitidos(usuario["areas"], organizacao.mapa_areas_rateios(db))
    execucoes = db.scalars(
        select(Execucao)
        .options(selectinload(Execucao.documentos), selectinload(Execucao.envios), selectinload(Execucao.tentativas))
        .order_by(Execucao.criado_em.desc())
    ).all()
    return [
        _execucao_dict(e) for e in execucoes if permitidos is None or e.tipo in permitidos
    ]


def _obter(db: Session, execucao_id: int) -> Execucao:
    execucao = db.scalar(
        select(Execucao)
        .options(selectinload(Execucao.documentos), selectinload(Execucao.envios), selectinload(Execucao.tentativas))
        .where(Execucao.id == execucao_id)
    )
    if execucao is None:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")
    return execucao


@router.get("/{execucao_id}")
def detalhe(
    execucao_id: int,
    usuario: dict = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> dict:
    execucao = _obter(db, execucao_id)
    area_map = organizacao.mapa_areas_rateios(db)
    _exigir_acesso(usuario, execucao.tipo, db)
    d = _execucao_dict(execucao, incluir_resultado=True)
    # Snapshot é gravado completo; redige salário/teto na leitura conforme o nível.
    pode_auditar = auth_service.pode_auditar(
        usuario["areas"], usuario.get("niveis", {}), execucao.tipo, area_map
    )
    d["resultado"] = redigir_resultado(d.get("resultado"), pode_auditar)
    d["pode_auditar"] = pode_auditar
    return d


# --- Exportações a partir do SNAPSHOT da execução -------------------------
# As exportações da tela de processamento leem o último resultado em memória; no
# histórico isso baixaria o arquivo de OUTRA execução (ou 404 em sessão nova).
# Aqui a fonte é o snapshot gravado, então o arquivo é sempre o da execução aberta.
CSV_ENCODING = "utf-8-sig"
CSV_SEPARADOR = ";"
# Colunas aninhadas (detalhamento) não cabem numa célula: ficam fora do CSV.
CSV_COLUNAS_IGNORADAS = frozenset({"por_tipo", "ocorrencias", "vidas"})
CSV_PJ_COLUNAS = ["nome", "cpf", "operadora", "valor_a_descontar"]
OPERADORA_LABEL = {"unimed": "Unimed", "bradesco": "Bradesco"}


def _valor_csv(valor: Any) -> str:
    """Célula do CSV: booleano legível e nada de None."""
    if isinstance(valor, bool):
        return "sim" if valor else "nao"
    return "" if valor is None else str(valor)


def _csv_resposta(linhas: list[list[str]], cabecalho: list[str], nome: str) -> StreamingResponse:
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=CSV_SEPARADOR, lineterminator="\n")
    escritor.writerow(cabecalho)
    escritor.writerows(linhas)
    return StreamingResponse(
        io.BytesIO(buffer.getvalue().encode(CSV_ENCODING)),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


def _secao_visivel(
    execucao: Execucao, usuario: dict, db: Session, secao: str = "itens"
) -> list[dict]:
    """Uma seção do snapshot, com salário/teto redigidos para quem não pode auditar."""
    area_map = organizacao.mapa_areas_rateios(db)
    pode_auditar = auth_service.pode_auditar(
        usuario["areas"], usuario.get("niveis", {}), execucao.tipo, area_map
    )
    resultado = redigir_resultado(execucao.resultado or {}, pode_auditar) or {}
    return [r for r in (resultado.get(secao) or []) if isinstance(r, dict)]


def _itens_visiveis(execucao: Execucao, usuario: dict, db: Session) -> list[dict]:
    """Atalho para a seção `itens` (usado pelo CSV de PJ)."""
    return _secao_visivel(execucao, usuario, db, "itens")


# Seções exportáveis do snapshot. `itens` é o detalhe por colaborador; `agregado`
# é o que virou o título no ERP (por centro de custo/classe) — é a seção que
# reconcilia o lançamento; `reconciliacao` cruza a NF com o rateado.
SECOES_CSV = ("itens", "agregado", "reconciliacao", "divergencias", "estornos", "totais")


@router.get("/{execucao_id}/resultado.csv")
def baixar_csv_execucao(
    execucao_id: int,
    secao: str = "itens",
    usuario: dict = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """CSV de uma seção do snapshot da execução (uma linha por registro).

    `secao` (query): itens (padrão) | agregado | reconciliacao | divergencias |
    estornos | totais. O detalhamento do LANÇAMENTO é o `agregado`: cada linha é
    um centro de custo/classe que compõe o título gerado no ERP.
    """
    if secao not in SECOES_CSV:
        raise HTTPException(
            status_code=422,
            detail=f"Seção inválida: {secao!r}. Use uma de: {', '.join(SECOES_CSV)}.",
        )
    execucao = _obter(db, execucao_id)
    _exigir_acesso(usuario, execucao.tipo, db)
    registros = _secao_visivel(execucao, usuario, db, secao)
    if not registros:
        raise HTTPException(
            status_code=404, detail=f"Execução sem dados na seção '{secao}' para exportar."
        )
    # União das chaves presentes, em ordem estável (registros podem divergir).
    colunas = [
        c for c in dict.fromkeys(k for r in registros for k in r)
        if c not in CSV_COLUNAS_IGNORADAS
    ]
    linhas = [[_valor_csv(r.get(c)) for c in colunas] for r in registros]
    return _csv_resposta(
        linhas, colunas, f"{secao}_{execucao.tipo}_{execucao.id}.csv"
    )


@router.get("/{execucao_id}/pj.csv")
def baixar_pj_csv_execucao(
    execucao_id: int,
    usuario: dict = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """CSV dos colaboradores PJ da execução (desconto cobrado na nota fiscal)."""
    execucao = _obter(db, execucao_id)
    _exigir_acesso(usuario, execucao.tipo, db)
    total = Decimal("0")
    linhas: list[list[str]] = []
    for item in _itens_visiveis(execucao, usuario, db):
        if not item.get("pj"):
            continue
        valor = Decimal(str(item.get("valor_descontado", "0") or "0"))
        if valor <= 0:
            continue
        operadora = str(item.get("operadora") or "").lower()
        linhas.append([
            str(item.get("nome") or ""),
            str(item.get("cpf") or ""),
            OPERADORA_LABEL.get(operadora, operadora.title()),
            f"{valor:.2f}".replace(".", ","),
        ])
        total += valor
    if not linhas:
        raise HTTPException(status_code=404, detail="Execução sem colaboradores PJ.")
    linhas.append(["TOTAL", "", "", f"{total:.2f}".replace(".", ",")])
    return _csv_resposta(linhas, CSV_PJ_COLUNAS, f"pj_{execucao.tipo}_{execucao.id}.csv")


@router.get("/{execucao_id}/documentos/{doc_id}")
def baixar_documento(
    execucao_id: int,
    doc_id: int,
    usuario: dict = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    execucao = _obter(db, execucao_id)
    _exigir_acesso(usuario, execucao.tipo, db)
    doc = next((d for d in execucao.documentos if d.id == doc_id), None)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return StreamingResponse(
        io.BytesIO(doc.conteudo),
        media_type=doc.mime or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc.nome}"'},
    )


class EnvioRequest(BaseModel):
    """Corpo opcional do envio. Hoje só a coparticipação usa (e exige) o campo."""

    competencia_pagamento: str | None = None


@router.post("/{execucao_id}/enviar")
async def enviar(
    execucao_id: int,
    body: EnvioRequest | None = None,
    settings: Settings = Depends(get_settings),
    usuario: dict = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> dict:
    """Envia (ou reenvia) a execução ao ERP. Idempotente: pula empresas já enviadas.

    Rateios de desconto em folha (coparticipação) exigem
    `competencia_pagamento` (AAAAMM) no corpo: é a competência da FOLHA em que o
    desconto entra, informada no envio — distinta da competência dos eventos.
    """
    execucao = _obter(db, execucao_id)
    _exigir_acesso(usuario, execucao.tipo, db)

    if not _tem_capacidade(execucao.tipo, "lanca_no_erp"):
        raise HTTPException(status_code=422, detail="Envio ao ERP não disponível para este rateio.")

    # Idempotência / anti-duplicidade: empresas que JÁ têm título (status "enviado")
    # nunca são reenviadas — evita criar título duplicado quando outra empresa falha.
    # Na coparticipação a mesma trava evita descontar duas vezes do colaborador.
    ja_enviadas = {e.empresa for e in execucao.envios if e.status == "enviado"}
    # Empresa com pendências IDENTIFICADAS volta ao envio só com elas — vale para
    # `parcial` e para `erro`: um reenvio que falhou inteiro mantém a lista, e sem
    # esta regra o próximo mandaria a empresa toda, duplicando quem já entrou.
    pendentes_por_empresa = {
        e.empresa: _matriculas(e.matriculas_pendentes)
        for e in execucao.envios
        if e.status != "enviado" and _matriculas(e.matriculas_pendentes)
    }
    # Parcial SEM lista identificada não é reenviada: parte entrou na folha e não
    # sabemos qual, então reenviar duplicaria. A UI orienta o tratamento manual.
    # (Erro sem lista é seguro: nada entrou, o lote inteiro pode ir de novo.)
    parciais_sem_lista = [
        e.empresa for e in execucao.envios
        if e.status == "parcial" and not _matriculas(e.matriculas_pendentes)
    ]
    cfg_fiscal = organizacao_fiscal.carregar_config_fiscal(db)

    autor = usuario.get("email", "")
    # Destino da escrita no momento DESTE envio (auditoria; ver models/execucao.py).
    ambiente_erp = settings.protheus_write_ambiente
    base_erp = settings.protheus_write_base_url
    por_chave = {(e.empresa, e.referencia or ""): e for e in execucao.envios}
    # Envios já gravados durante o próprio envio (pelos eventos por título), para
    # a gravação final não repetir o registro nem duplicar o log da tentativa.
    persistidos: set[tuple[str, str]] = set()

    def _linha_envio(empresa: str, referencia: str) -> EnvioErp:
        """Linha de estado atual do envio, criada na primeira vez que é tocada."""
        chave = (empresa, referencia or "")
        row = por_chave.get(chave)
        if row is None:
            row = EnvioErp(empresa=empresa, referencia=chave[1])
            execucao.envios.append(row)
            por_chave[chave] = row
        return row

    def _gravar_envio(env: dict) -> None:
        """Estado atual do envio + log imutável da tentativa."""
        row = _linha_envio(env["empresa"], env.get("referencia") or "")
        # Trava defensiva: nunca sobrescrever uma empresa já integrada (com título).
        # "parcial" NÃO é integrada: o reenvio das pendentes precisa atualizá-la.
        if row.status == "enviado" and row.titulo:
            return
        row.rest = env["rest"]
        row.contrato = env["contrato"]
        row.titulo = env["titulo"]
        row.status = env["status"]
        row.mensagem = env["mensagem"]
        row.erp_ambiente = ambiente_erp
        row.erp_base_url = base_erp
        if "enviados" in env:
            # Lote da folha: contagens e pendências do ÚLTIMO envio desta empresa.
            row.enviados = env.get("enviados") or 0
            row.aceitos = env.get("aceitos") or 0
            row.matriculas_pendentes = env.get("matriculas_pendentes") or []
        execucao.tentativas.append(EnvioTentativa(
            empresa=env["empresa"], referencia=env.get("referencia") or "",
            rest=env["rest"], contrato=env["contrato"],
            titulo=env["titulo"], status=env["status"], mensagem=env["mensagem"],
            usuario=autor, erp_ambiente=ambiente_erp, erp_base_url=base_erp,
            resposta_erp=env.get("resposta"),
        ))
        persistidos.add((env["empresa"], env.get("referencia") or ""))

    def _evento_erp(evt: dict) -> None:
        """
        Grava CADA título assim que o ERP responde, com commit próprio.

        É o que dá progresso ao operador (a tela consulta o estado enquanto o
        envio corre) e o que garante que uma queda no meio não apague o que já
        entrou: sem isso, a gravação só acontecia depois do último documento, e
        um reenvio após timeout duplicaria os títulos já lançados.
        """
        if evt.get("fase") == "enviando":
            row = _linha_envio(evt["empresa"], evt.get("referencia") or "")
            if row.status == "enviado" and row.titulo:
                return
            row.rest = evt.get("rest", "")
            row.contrato = evt.get("contrato", "")
            row.titulo = ""
            row.status = "enviando"
            row.mensagem = "Aguardando a resposta do ERP."
            row.erp_ambiente = ambiente_erp
            row.erp_base_url = base_erp
        else:
            _gravar_envio(evt)
        db.commit()

    # Rotina de desconto em folha (GPE): sem contrato/NF/título — fluxo próprio.
    # A capacidade é detectada pelo módulo, como no export TXT.
    if _tem_capacidade(execucao.tipo, "gerar_payload_erp"):
        # No 1º envio a competência vem no corpo; no REENVIO pelo histórico ela já
        # está gravada na execução (é a folha usada na tentativa original) — pedir
        # de novo abriria espaço para lançar a mesma execução em outra folha.
        comp_pagamento = re.sub(
            r"\D", "", (body.competencia_pagamento if body else "") or execucao.competencia or ""
        )
        if len(comp_pagamento) != 6:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Informe a competência de pagamento no formato AAAAMM (ex.: 202608) "
                    "— é a folha em que o desconto será lançado."
                ),
            )
        resultado_envio = await erp.enviar_coparticipacao(
            settings, cfg_fiscal, execucao.tipo, execucao.resultado or {}, comp_pagamento,
            ja_enviadas | set(parciais_sem_lista), pendentes_por_empresa,
        )
        for empresa in parciais_sem_lista:
            resultado_envio.setdefault("alertas", []).append(
                f"Empresa '{empresa}': o ERP não identificou quais registros recusou, "
                f"então o reenvio automático foi bloqueado (mandaria tudo de novo e "
                f"duplicaria quem já entrou). Trate pelo TXT ou manualmente."
            )
    elif _tem_capacidade(execucao.tipo, "titulos_erp"):
        # Um título por documento (telefonia: um por boleto), todos numa empresa.
        # Documento que ficou "enviando": o envio anterior caiu entre o POST e a
        # resposta, então NÃO se sabe se o título entrou. Reenviar às cegas
        # duplicaria; ficar parado esconderia o caso. Vira erro com instrução, é
        # pulado NESTE envio, e no próximo pode ser reenviado se não entrou.
        interrompidos = [e for e in execucao.envios if e.status == "enviando"]
        avisos_interrompidos: list[str] = []
        for row in interrompidos:
            row.status = "erro"
            row.mensagem = (
                "O envio anterior foi interrompido antes da resposta do ERP. Confira no "
                f"Protheus se o título da conta {row.referencia or row.empresa} entrou. "
                "Se não entrou, repita o envio. Se entrou, não reenvie este documento: "
                "ele precisa ser tratado manualmente no ERP."
            )
            execucao.tentativas.append(EnvioTentativa(
                empresa=row.empresa, referencia=row.referencia or "", rest=row.rest,
                contrato=row.contrato, titulo="", status="erro", mensagem=row.mensagem,
                usuario=autor, erp_ambiente=ambiente_erp, erp_base_url=base_erp,
            ))
            avisos_interrompidos.append(row.mensagem)
        if interrompidos:
            db.commit()
        enviadas_com_ref = {
            (e.empresa, e.referencia or "") for e in execucao.envios if e.status == "enviado"
        } | {(e.empresa, e.referencia or "") for e in interrompidos}
        resultado_envio = await erp.enviar_titulos_por_referencia(
            settings, cfg_fiscal, execucao.tipo, execucao.resultado or {},
            settings.protheus_claro_empresa, enviadas_com_ref, on_evento=_evento_erp,
        )
        resultado_envio.setdefault("alertas", []).extend(avisos_interrompidos)
    else:
        resultado_envio = await erp.enviar_rateio(
            settings, cfg_fiscal, execucao.tipo, execucao.resultado or {}, execucao.competencia, ja_enviadas
        )

    # Persiste (upsert) o ESTADO ATUAL por empresa SEMPRE — inclusive quando o grupo
    # AE ficou bloqueado, pois pré-notas independentes podem ter sido enviadas.
    # Chave (empresa, referência): a telefonia gera um título por BOLETO na mesma
    # empresa, então a empresa sozinha não identifica o envio. O que os eventos
    # por título já gravaram durante o envio não é regravado.
    for env in resultado_envio["envios"]:
        if (env["empresa"], env.get("referencia") or "") in persistidos:
            continue
        _gravar_envio(env)
    db.flush()

    # Status: "enviado" só quando TODAS as empresas do rateio foram enviadas.
    empresas_rateio = _unidades_do_snapshot(execucao.tipo, execucao.resultado or {})
    enviadas = {
        (
            f"{e.empresa.strip().upper()}|{e.referencia}" if e.referencia
            else e.empresa.strip().upper()
        )
        for e in execucao.envios if e.status == "enviado"
    }
    if empresas_rateio and empresas_rateio <= enviadas:
        execucao.status = "enviado"
    elif any(e.status == "erro" for e in execucao.envios):
        execucao.status = "erro_envio"
    elif any(e.status == "parcial" for e in execucao.envios):
        # Parte do lote entrou na folha: nem pendente (já lançou), nem erro (a
        # maioria passou). O reenvio trata só as matrículas recusadas.
        execucao.status = "parcial"
    else:
        execucao.status = "pendente_envio"
    db.commit()
    db.refresh(execucao)
    return {
        "bloqueado": resultado_envio["bloqueado"],
        "bloqueios": resultado_envio.get("bloqueios", []),
        "alertas": resultado_envio.get("alertas", []),
        "status": execucao.status,
        "envios": [_envio_dict(e) for e in execucao.envios],
        "tentativas": [
            _tentativa_dict(t) for t in sorted(execucao.tentativas, key=lambda x: x.id)
        ],
    }


@router.post("/{execucao_id}/notificar-fiscal")
def notificar_fiscal(
    execucao_id: int,
    settings: Settings = Depends(get_settings),
    usuario: dict = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> dict:
    """
    Envia ao dep. fiscal (por e-mail) os nº dos títulos + NF/boleto em anexo.
    Endpoint SÍNCRONO (smtplib bloqueia) — o FastAPI o roda em threadpool.
    """
    execucao = _obter(db, execucao_id)
    _exigir_acesso(usuario, execucao.tipo, db)

    if not any(e.status == "enviado" for e in execucao.envios):
        raise HTTPException(status_code=422, detail="Nenhum título gerado ainda — envie ao ERP antes de notificar o fiscal.")
    # Um título por documento (telefonia): o fiscal recebe UM e-mail com todos os
    # boletos e todos os títulos, então só depois que todos entraram. Lançar 7 de 8
    # é envio parcial — notificar aqui obrigaria a um segundo e-mail depois.
    if _tem_capacidade(execucao.tipo, "titulos_erp") and execucao.status != "enviado":
        pendentes = _unidades_do_snapshot(execucao.tipo, execucao.resultado or {}) - {
            f"{e.empresa.strip().upper()}|{e.referencia}" for e in execucao.envios
            if e.status == "enviado"
        }
        raise HTTPException(
            status_code=422,
            detail=(
                f"{len(pendentes)} documento(s) ainda não lançado(s) no ERP. "
                "A notificação ao fiscal reúne todos os títulos num envio só — "
                "conclua o lançamento antes de notificar."
            ),
        )
    # Para = fiscal (cadastro, com o .env como valor inicial); Cópia = cópia
    # permanente + e-mails da área dona do processo; Reply-To = a área, para a
    # resposta do fiscal cair em quem tratou o rateio.
    envio_para = notificacao_config.resolver(db, settings, execucao.tipo)
    destinatarios = envio_para["para"]
    if not destinatarios:
        raise HTTPException(
            status_code=422,
            detail=(
                "Nenhum destinatário do departamento fiscal cadastrado. "
                "Informe em Configurações › Organização › Notificações."
            ),
        )
    # Área do processo: o rateio pode estar em mais de uma (raro) — todas entram.
    area_map = organizacao.mapa_areas_rateios(db)
    areas = sorted(nome for nome, tipos in area_map.items() if execucao.tipo in tipos)
    try:
        notif = notificacao.montar_notificacao(
            settings, organizacao_fiscal.carregar_config_fiscal(db), execucao, " / ".join(areas)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        email.enviar_email(
            settings, destinatarios, notif["assunto"], notif["corpo"], notif["anexos"],
            corpo_html=notif.get("corpo_html"),
            imagens_inline=notif.get("imagens_inline"),
            copia=envio_para["copia"],
            responder_para=envio_para["reply_to"],
        )
    except email.EmailError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    execucao.notificado_em = dt.datetime.now(dt.UTC)
    # Guarda a quem foi: os cadastros mudam, e sem isso o histórico não responde
    # quem recebeu a notificação de um processo antigo.
    execucao.notificado_para = {"para": destinatarios, "copia": envio_para["copia"]}
    db.commit()
    db.refresh(execucao)
    return {
        "ok": True,
        "destinatarios": destinatarios,
        "copia": envio_para["copia"],
        "notificado_em": execucao.notificado_em.isoformat() if execucao.notificado_em else None,
    }
