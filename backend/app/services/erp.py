"""
Envio do rateio ao ERP via Autorização de Entrega (AE) sobre Contrato de Parceria.

Fluxo por empresa (cada NF -> uma empresa -> um rest -> um título):
1. GET dos contratos de parceria disponíveis do fornecedor (operadora) na empresa.
2. Escolhe o contrato mais recente (por C3_EMISSAO).
3. Casa cada linha do rateio (centro de custo + classe) com um item do contrato
   (C3_CC + C3_CLVL), referenciando C3_NUM/C3_ITEM na AE.
4. TRAVA DE SEGURANÇA: se QUALQUER empresa pendente ficar sem contrato ou tiver
   centro de custo sem item no contrato, NADA é enviado (evita lançamento parcial).
5. Sem bloqueios: POST da AE por empresa; interpreta a resposta (título/erro).

Puro quanto a regra de casamento/trava; o acesso HTTP fica em `services.protheus`.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from collections import defaultdict
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.config import Settings
from app.services import protheus
from app.services.organizacao_fiscal import ConfigFiscal

logger = logging.getLogger(__name__)

_RE_TITULO = re.compile(r"documento:\s*([A-Za-z0-9\-/.]+)", re.IGNORECASE)
_CENTAVOS = Decimal("0.01")


def _distribuir_estorno(linhas: list[dict], estorno: Decimal) -> list[dict]:
    """
    Distribui o estorno (valor NEGATIVO) proporcionalmente ao valor de cada linha,
    para a soma da AE bater com a NF (rateado + estornos). O resíduo de
    arredondamento vai para a maior linha, garantindo soma exata.
    """
    total = sum((l["valor"] for l in linhas), Decimal("0"))
    if not linhas or estorno == 0 or total <= 0:
        return linhas
    novas: list[dict] = []
    acumulado = Decimal("0")
    for l in linhas:
        parte = (estorno * l["valor"] / total).quantize(_CENTAVOS, ROUND_HALF_UP)
        acumulado += parte
        novas.append({**l, "valor": l["valor"] + parte})
    residuo = estorno - acumulado  # ~0; corrige na maior linha para bater exato
    if residuo != 0:
        idx = max(range(len(novas)), key=lambda i: linhas[i]["valor"])
        novas[idx]["valor"] = novas[idx]["valor"] + residuo
    return novas


def _operadora_do_tipo(tipo: str) -> str:
    """
    Fornecedor do rateio — é o CNPJ dele que busca o contrato de parceria.

    Preferência para o que o MÓDULO declara (`fornecedor`); sem declaração, cai na
    dedução pelo nome do tipo, que é como os rateios de plano de saúde funcionam.
    """
    try:
        declarado = str(getattr(_modulo_de(tipo), "fornecedor", "") or "").strip()
    except KeyError:
        declarado = ""
    if declarado:
        return declarado
    return "bradesco" if "bradesco" in tipo else "unimed"


def _cnpj_fornecedor(settings: Settings, cfg: ConfigFiscal, operadora: str) -> str:
    """
    CNPJ do fornecedor: o CADASTRO de fornecedores manda; a config é o padrão.

    Sem o fallback, um fornecedor novo (ex.: a Claro na telefonia) exige cadastro
    manual antes do primeiro lançamento, e a falha aparece como "CNPJ do fornecedor
    não cadastrado" — sem dizer onde cadastrar.
    """
    return (
        cfg.fornecedor_cnpj(operadora)
        or settings.protheus_fornecedor_cnpj.get(operadora, "")
    ).strip()


def _modulo_de(tipo: str) -> Any:
    """Módulo de rateio registrado para o tipo (import tardio evita ciclo)."""
    from app.modules.registry import registry

    return registry.get(tipo)


def _emissao_hoje() -> str:
    return dt.date.today().strftime("%Y%m%d")


def _chave(cc: Any, clvl: Any) -> tuple[str, str]:
    return (str(cc or "").strip(), str(clvl or "").strip())


def _agrupar_por_numero(contratos: list[dict]) -> list[dict]:
    """
    O endpoint pode devolver o MESMO contrato (C3_NUM) partido em várias entradas
    (blocos de itens sequenciais). Junta os itens do mesmo número num único
    contrato, para a cobertura e o casamento CC->item verem o contrato inteiro.
    """
    merged: dict[str, dict] = {}
    for c in contratos:
        header = c.get("HEADER") or {}
        num = str(header.get("C3_NUM", ""))
        if num not in merged:
            merged[num] = {"HEADER": header, "ITEMS": list(c.get("ITEMS") or [])}
        else:
            merged[num]["ITEMS"].extend(c.get("ITEMS") or [])
    return list(merged.values())


def _cod_fornecedor(cnpj: str) -> str:
    """
    Código do fornecedor como o Protheus o espera na AE (`C7_FORNECE`): os 8
    PRIMEIROS dígitos do CNPJ (ex.: 45678910000166 -> "45678910"), que é a
    convenção do cadastro SA2 aqui. Derivar do CNPJ (e não copiar o
    `C3_FORNECE` do contrato) mantém o título no fornecedor que o rateio
    resolveu no cadastro, e evita o erro "Tabela SA2 / Inconsistência" quando o
    contrato traz o campo em outro formato.
    """
    return re.sub(r"\D", "", cnpj or "")[:8]


def _escolher_contrato(contratos: list[dict], ccs: set[str]) -> dict | None:
    """
    Escolhe o contrato que melhor COBRE os centros de custo do rateio (o ERP exige
    que cada item referencie um item de contrato com o mesmo CC). Empate -> emissão
    mais recente (C3_EMISSAO em AAAAMMDD).
    """
    if not contratos:
        return None

    def cobertura(c: dict) -> int:
        contrato_ccs = {str(i.get("C3_CC", "")).strip() for i in (c.get("ITEMS") or [])}
        return len(ccs & contrato_ccs)

    return max(
        contratos,
        key=lambda c: (cobertura(c), str((c.get("HEADER") or {}).get("C3_EMISSAO", ""))),
    )


def _montar_payload(contrato: dict, linhas: list[dict], obs: str, cnpj: str = "") -> tuple[dict, list[str]]:
    """Monta o payload da AE a partir do contrato e das linhas do rateio da empresa.

    Envio INTEGRAL: TODOS os centros de custo do rateio entram. Quando o CC+classe
    existe no contrato, usa o item correspondente (produto/armazém/item). Quando NÃO
    existe, o CC entra do mesmo jeito referenciando o contrato (produto/armazém/nº
    vêm do 1º item, que é uniforme). Retorna (payload, ccs_fora_do_contrato) apenas
    para fins informativos — NÃO impede o envio.
    """
    header = contrato.get("HEADER") or {}
    contrato_itens = contrato.get("ITEMS") or []
    idx: dict[tuple[str, str], dict] = {}
    idx_cc: dict[str, dict] = {}
    for item in contrato_itens:
        idx.setdefault(_chave(item.get("C3_CC"), item.get("C3_CLVL")), item)
        idx_cc.setdefault(str(item.get("C3_CC", "")).strip(), item)

    itens_payload: list[dict] = []
    fora_contrato: list[str] = []
    for linha in linhas:
        cc = str(linha["centro_custo"]).strip()
        classe = str(linha["classe_valor"]).strip()
        # Casa por (CC+classe); se não tiver classe (ex.: PJ do cadastro), casa só por CC.
        ci = idx.get(_chave(cc, classe)) or idx_cc.get(cc)
        if ci is None:
            # CC não existe no contrato: NÃO referencia item inválido (o ERP rejeita).
            fora_contrato.append(cc)
            continue
        # Classe de valor vem do CONTRATO quando a linha não traz (PJ sem classe).
        classe_final = classe or str(ci.get("C3_CLVL", "")).strip()
        valor = round(float(linha["valor"]), 2)
        itens_payload.append({
            "C7_PRODUTO": ci.get("C3_PRODUTO"),
            "C7_QUANT": 1,
            "C7_PRECO": valor,
            "C7_TOTAL": valor,
            "C7_LOCAL": ci.get("C3_LOCAL"),
            "C7_OBS": obs,
            "C7_CC": cc,
            "C7_CLVL": classe_final,
            "C7_NUMSC": ci.get("C3_NUM") or header.get("C3_NUM"),
            "C7_ITEMSC": ci.get("C3_ITEM"),
        })

    payload = {
        "HEADER": {
            "C7_FILIAL": header.get("C3_FILIAL"),
            # Fornecedor: código derivado do CNPJ do cadastro (ver `_cod_fornecedor`);
            # o contrato só responde por ele quando não há CNPJ resolvido.
            "C7_FORNECE": _cod_fornecedor(cnpj) or header.get("C3_FORNECE"),
            "C7_LOJA": header.get("C3_LOJA"),
            "C7_COND": header.get("C3_COND"),
            "C7_EMISSAO": _emissao_hoje(),
            "C7_MOEDA": header.get("C3_MOEDA", 1),
            "C7_CONTATO": "RATEIO",
            "C7_FILENT": header.get("C3_FILENT") or header.get("C3_FILIAL"),
            "C7_TXMOEDA": header.get("C3_TXMOEDA", 0),
        },
        "ITENS": itens_payload,
    }
    return payload, fora_contrato


def _serie_prenota(bruto: Any) -> str:
    """
    Série da NF para a pré-nota: mapeada da própria nota, mas o Protheus valida
    F1_SERIE em no máximo 3 caracteres. Removemos zeros à esquerda ("0001" -> "1")
    e limitamos a 3 chars; se ficar vazia (ex.: "0000"), assume "1".
    """
    s = str(bruto or "").strip().lstrip("0")
    return (s or "1")[:3]


def _montar_payload_prenota(
    prenota_produto: str, prenota_filial: str, cnpj: str, nf: dict, linhas: list[dict],
) -> dict:
    """
    Monta o payload da PRÉ-NOTA (entrada de nota). Sem contrato: produto/filial vêm
    do cadastro da empresa; número/série/emissão vêm da NF; um item por CC do rateio
    (já com estornos distribuídos). QUANT=1, VUNIT=TOTAL=valor.
    """
    header = {
        "FORNECEDOR": cnpj,
        "F1_FILIAL": prenota_filial,
        "F1_TIPO": "N",
        "F1_FORMUL": "N",
        "F1_DOC": nf.get("numero", ""),
        "F1_SERIE": _serie_prenota(nf.get("serie")),
        "F1_EMISSAO": nf.get("emissao", ""),
        "F1_ESPECIE": "RPS",
        "F1_COND": "000",
    }
    def _num(v):  # D1_CC/D1_CLVL vão como número (conforme a spec); fallback p/ string.
        s = str(v).strip()
        return int(s) if s.isdigit() else s

    itens = []
    for linha in linhas:
        valor = round(float(linha["valor"]), 2)
        itens.append({
            "D1_COD": prenota_produto,
            "D1_QUANT": 1,
            "D1_VUNIT": valor,
            "D1_TOTAL": valor,
            "D1_CC": _num(linha["centro_custo"]),
            "D1_CLVL": _num(linha["classe_valor"]),
        })
    return {"HEADER": header, "ITENS": itens}


def _interpretar_resposta(resp: dict) -> dict:
    """Interpreta a resposta do POST -> {ok, titulo, mensagem}.

    Sucesso exige 2xx, ausência de campos de erro e um sinal explícito de sucesso
    (code 200/201 OU "documento"/"sucesso" na mensagem). Assim, um 2xx com corpo
    inesperado NÃO é marcado como enviado por engano.
    """
    body = resp.get("body") or {}
    status = resp.get("http_status", 0)
    code = body.get("code")
    msg = str(body.get("message", "") or "")
    tem_erro = "errorCode" in body or "errorMessage" in body or "errors" in body
    sinal_ok = code in (200, 201) or "documento" in msg.lower() or "sucesso" in msg.lower()
    if (200 <= status < 300) and not tem_erro and sinal_ok:
        # O número do título/documento vem no campo `id`; fallback: regex na mensagem.
        titulo = str(body.get("id") or "").strip()
        if not titulo:
            m = _RE_TITULO.search(msg)
            titulo = m.group(1) if m else ""
        return {"ok": True, "titulo": titulo, "mensagem": msg}

    # Erro: monta uma mensagem legível a partir de errorMessage + errors[] (detalhe
    # por campo/regra) + detailedMessage. Normaliza \r\n para quebras de linha limpas.
    partes: list[str] = []
    em = str(body.get("errorMessage", "") or "").strip()
    if em:
        partes.append(em)
    for e in body.get("errors") or []:
        detalhe = str((e or {}).get("message", "") or "").strip()
        if detalhe:
            partes.append(detalhe)
    dm = str(body.get("detailedMessage", "") or "").strip()
    if dm:
        partes.append(dm)
    mensagem = "\n\n".join(partes).strip() or msg or str(body)
    mensagem = mensagem.replace("\r\n", "\n").replace("\r", "\n")
    return {"ok": False, "titulo": "", "mensagem": mensagem}


def _linhas_por_empresa(agregado: list[dict]) -> dict[str, list[dict]]:
    grupos: dict[str, list[dict]] = defaultdict(list)
    for a in agregado:
        empresa = str(a.get("empresa", "")).strip()
        valor = Decimal(str(a.get("valor", "0")))
        if not empresa or valor == 0:
            continue
        grupos[empresa].append({
            "centro_custo": str(a.get("centro_custo", "")),
            "classe_valor": str(a.get("classe_valor", "")),
            "valor": valor,
        })
    return dict(grupos)


def _recon_por_empresa(resultado: dict) -> dict[str, dict]:
    """Mapa empresa (upper) -> item de reconciliação do snapshot."""
    mapa: dict[str, dict] = {}
    for r in resultado.get("reconciliacao") or []:
        mapa[str(r.get("empresa", "")).strip().upper()] = r
    return mapa


def _estorno_por_empresa(resultado: dict) -> dict[str, Decimal]:
    """Soma dos estornos (valores negativos) por empresa (chave upper)."""
    mapa: dict[str, Decimal] = defaultdict(Decimal)
    for e in resultado.get("estornos") or []:
        mapa[str(e.get("empresa", "")).strip().upper()] += Decimal(str(e.get("valor", "0")))
    return mapa


async def enviar_rateio(
    settings: Settings,
    cfg: ConfigFiscal,
    tipo: str,
    resultado: dict,
    competencia: str,
    ja_enviadas: set[str] | None = None,
) -> dict:
    """
    Orquestra o envio ao ERP a partir do snapshot `resultado` (agregado +
    reconciliação). `ja_enviadas` = empresas já enviadas (reenvio pula).

    Roteia POR EMPRESA: rotina "ae" (Autorização de Entrega) segue o fluxo abaixo;
    rotina "pre_nota" (ex.: Zenith) fica PENDENTE (endpoint em preparação) e NÃO
    impede o envio das demais.

    Para as empresas de rota AE, TRAVAS (qualquer uma -> nenhuma AE é enviada):
    1. Reconciliação: a NF da empresa deve BATER com o rateado.
    2. Contrato: a empresa precisa ter contrato de parceria disponível.
    CC sem item no contrato NÃO trava — entra no envio integral.

    Retorna {bloqueado, bloqueios: [str], alertas: [str], envios: [{empresa, rest,
    contrato, titulo, status: enviado|erro|pendente, mensagem}]}.
    """
    ja_enviadas = ja_enviadas or set()
    operadora = _operadora_do_tipo(tipo)
    cnpj = _cnpj_fornecedor(settings, cfg, operadora)
    obs = f"Rateio {operadora.upper()} {competencia}".strip()

    grupos = _linhas_por_empresa(resultado.get("agregado") or [])
    pendentes = {e: linhas for e, linhas in grupos.items() if e not in ja_enviadas}
    recon = _recon_por_empresa(resultado)
    estornos_emp = _estorno_por_empresa(resultado)

    bloqueios: list[str] = []      # travas do GRUPO AE (anti-parcial)
    alertas: list[str] = []
    preparados: list[dict] = []    # AE prontos p/ postar {empresa, rest, contrato_num, payload}
    envios: list[dict] = []        # resultados por empresa (pré-nota inline + AE)

    for empresa, linhas in pendentes.items():
        chave = empresa.strip().upper()
        rotina = cfg.rotina_erp(empresa)
        rest = cfg.rest_da_empresa(empresa)
        # Gate de reconciliação (comum às duas rotinas): a NF deve bater com o rateado.
        r = recon.get(chave)
        recon_erro = None
        if r is None:
            recon_erro = f"Empresa '{empresa}': sem reconciliação com a NF — anexe a NF e reprocesse antes de enviar."
        elif not r.get("bate"):
            recon_erro = (
                f"Empresa '{empresa}': a NF não confere com o rateado "
                f"(documento {r.get('valor_documento')} × rateado {r.get('valor_base')}) — corrija antes de enviar."
            )
        # Estornos (negativos) distribuídos proporcionalmente -> soma bate com a NF.
        linhas = _distribuir_estorno(linhas, estornos_emp.get(chave, Decimal("0")))

        if rotina == "pre_nota":
            # Pré-nota: independente (não participa da trava do grupo AE).
            # `empresa`/`rest` vêm por default: fixa os valores DESTA iteração,
            # em vez de resolvê-los quando a função for chamada.
            def _falha(msg, empresa=empresa, rest=rest):
                envios.append({"empresa": empresa, "rest": rest or "", "contrato": "",
                               "titulo": "", "status": "erro", "mensagem": msg})
            if recon_erro:
                _falha(recon_erro)
                continue
            if not rest:
                _falha(f"Empresa '{empresa}' sem rest mapeado no Protheus.")
                continue
            numero = str((r or {}).get("numero_documento") or "").strip()
            emissao = str((r or {}).get("emissao_documento") or "").strip()
            serie = str((r or {}).get("serie_documento") or "").strip()
            if not numero or not emissao:
                _falha(f"Empresa '{empresa}': não foi possível extrair número/data da NF para a pré-nota.")
                continue
            prenota_produto, prenota_filial = cfg.prenota(empresa)
            payload = _montar_payload_prenota(prenota_produto, prenota_filial, cnpj, {"numero": numero, "emissao": emissao, "serie": serie}, linhas)
            try:
                resp = await protheus.incluir_pre_nota(settings, rest, payload)
                res = _interpretar_resposta(resp)
            except protheus.ProtheusError as exc:
                res = {"ok": False, "titulo": "", "mensagem": f"Falha de comunicação com o ERP: {exc}"}
            # A pré-nota tem o MESMO número da NF: devolve o nº da NF como "título"
            # (igual à Vertex) para o usuário consultar na Zenith.
            envios.append({"empresa": empresa, "rest": rest, "contrato": "",
                           "titulo": numero if res["ok"] else (res["titulo"] or ""),
                           "status": "enviado" if res["ok"] else "erro", "mensagem": res["mensagem"]})
            continue

        # Rota AE (grupo anti-parcial): reconciliação/contrato bloqueiam TODAS as AE.
        if recon_erro:
            bloqueios.append(recon_erro)
            continue
        if not rest:
            bloqueios.append(f"Empresa '{empresa}' sem rest mapeado no Protheus.")
            continue
        try:
            contratos = _agrupar_por_numero(await protheus.buscar_contratos(settings, rest, cnpj))
        except protheus.ProtheusError as exc:
            bloqueios.append(f"Empresa '{empresa}': falha ao buscar contrato ({exc}).")
            continue
        contrato = _escolher_contrato(contratos, {str(l["centro_custo"]).strip() for l in linhas})
        if contrato is None:
            bloqueios.append(
                f"Não há contrato de parceria disponível para a empresa {empresa}. "
                f"Crie o contrato no ERP para {empresa} antes de enviar o rateio."
            )
            continue
        payload, faltantes = _montar_payload(contrato, linhas, obs, cnpj)
        if faltantes:
            num_contrato = str((contrato.get("HEADER") or {}).get("C3_NUM", ""))
            bloqueios.append(
                f"Empresa '{empresa}': os centros de custo a seguir não estão no contrato "
                f"{num_contrato} — inclua-os no contrato no ERP antes de enviar: "
                + ", ".join(sorted(set(faltantes))) + "."
            )
            continue
        preparados.append({
            "empresa": empresa, "rest": rest,
            "contrato_num": str((contrato.get("HEADER") or {}).get("C3_NUM", "")),
            "payload": payload,
        })

    # Grupo AE: se houver QUALQUER bloqueio, nenhuma AE é postada (anti-parcial).
    # As pré-notas já processadas acima permanecem em `envios`.
    if not bloqueios:
        for prep in preparados:
            try:
                resp = await protheus.incluir_autorizacao_entrega(settings, prep["rest"], prep["payload"])
                res = _interpretar_resposta(resp)
            except protheus.ProtheusError as exc:
                res = {"ok": False, "titulo": "", "mensagem": f"Falha de comunicação com o ERP: {exc}"}
            envios.append({
                "empresa": prep["empresa"], "rest": prep["rest"], "contrato": prep["contrato_num"],
                "titulo": res["titulo"], "status": "enviado" if res["ok"] else "erro", "mensagem": res["mensagem"],
            })

    return {"bloqueado": bool(bloqueios), "bloqueios": bloqueios, "alertas": alertas, "envios": envios}


# --- Coparticipação (desconto em folha, rotina GPE) --------------------------
# Outro fluxo: sem contrato, sem NF, sem título. Um POST em LOTE por empresa
# (o rest da URL é a empresa), com uma entrada por matrícula.

# O ERP identifica o registro recusado pela POSIÇÃO no lote, contando de 1
# ("item_26" = 26ª entrada) — confirmado com um lote de duas matrículas inválidas,
# que voltou item_1/item_2. E enterra o motivo real dentro de `detailedMessage`,
# num bloco "Mensagem do erro:  [ ... ]".
_RE_ITEM = re.compile(r"^item_(\d+)$", re.IGNORECASE)
_RE_MOTIVO = re.compile(r"Mensagem do erro:\s*\[\s*(.*?)\s*\]", re.DOTALL)


def _motivo_do_erro(detalhe: dict) -> str:
    """Extrai o motivo legível: o texto do ERP vem embrulhado em metadados do form."""
    bruto = str(detalhe.get("detailedMessage") or "")
    achado = _RE_MOTIVO.search(bruto)
    if achado and achado.group(1).strip():
        return achado.group(1).strip()
    return str(detalhe.get("errorMessage") or detalhe.get("message") or "").strip()


def _erros_copart(body: dict, rotulos: dict[int, str] | None = None) -> list[str]:
    """
    Mensagens de erro do corpo, tanto do 4xx quanto do 200 com falhas parciais.

    O formato conhecido é `errors: [{field, code, message}]` (4xx) e
    `errors: {"erros": [{"item_N": {...}}]}` (200). Como já houve 200 parcial SEM
    detalhe algum, varremos qualquer lista dentro de `errors`, sob qualquer chave:
    um detalhe que o ERP mande numa chave nova é a única pista de QUAIS registros
    falharam, e descartá-la por não reconhecer o campo é perder a informação.

    `rotulos` traduz a posição no lote em pessoa (ex.: 26 -> "Thayna (mat 001121)"),
    para o erro dizer QUEM ficou sem desconto em vez de um índice.
    """
    bruto = body.get("errors")
    itens: list[Any] = []
    if isinstance(bruto, list):
        itens = bruto
    elif isinstance(bruto, dict):
        for valor in bruto.values():
            if isinstance(valor, list):
                itens.extend(valor)
            elif isinstance(valor, (str, int)) and str(valor).strip():
                itens.append(valor)
    elif isinstance(bruto, str) and bruto.strip():
        itens = [bruto]

    mensagens: list[str] = []
    for e in itens:
        if isinstance(e, dict):
            # {"item_26": {errorCode, errorMessage, detailedMessage}} -> quem + motivo.
            if len(e) == 1:
                (chave, valor), = e.items()
                achado = _RE_ITEM.match(str(chave))
                if achado and isinstance(valor, dict):
                    posicao = int(achado.group(1))
                    quem = (rotulos or {}).get(posicao) or f"registro {posicao}"
                    mensagens.append(f"{quem} — {_motivo_do_erro(valor)}")
                    continue
            campo = str(e.get("field") or "").strip()
            msg = str(e.get("message") or e.get("code") or "").strip()
            if not campo and not msg:
                # Formato desconhecido: melhor mostrar cru do que engolir.
                mensagens.append(str(e))
            else:
                mensagens.append(f"{campo}: {msg}" if campo and msg else (msg or campo))
        else:
            mensagens.append(str(e))
    return [m for m in mensagens if m]


def _interpretar_resposta_copart(
    resp: dict, enviados: int, rotulos: dict[int, str] | None = None
) -> dict:
    """
    Interpreta a resposta do POST de coparticipação -> {ok, aceitos, mensagem}.

    Sucesso: HTTP 200 com `totalOk` == registros enviados e sem erros. O ERP pode
    responder 200 com falha PARCIAL (`totalOk` menor que o enviado e/ou
    `errors.erros` preenchido) — isso NÃO é sucesso: parte da folha ficou sem
    desconto e alguém precisa agir. Por isso a contagem entra na mensagem.
    """
    status = int(resp.get("http_status") or 0)
    body = resp.get("body")
    if not isinstance(body, dict):
        return {"ok": False, "aceitos": 0, "mensagem": f"HTTP {status}: resposta inesperada do ERP."}

    erros = _erros_copart(body, rotulos)
    aceitos_bruto = body.get("totalOk")
    try:
        # `totalOk` pode vir ausente ou não numérico: o except abaixo é a regra.
        aceitos = int(aceitos_bruto)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        aceitos = 0

    if status == 200 and not erros and aceitos == enviados:
        return {
            "ok": True,
            "aceitos": aceitos,
            "mensagem": f"{aceitos} matrícula(s) incluída(s) na folha.",
        }

    # UMA informação por LINHA: tudo numa linha só (contagem + N motivos + HTTP)
    # fazia o usuário se perder no meio da frase. A UI renderiza com pre-wrap.
    linhas: list[str] = []
    if aceitos_bruto is not None:
        linhas.append(f"{aceitos} de {enviados} incluído(s) na folha.")
    if erros:
        linhas.append("Não incluídos:")
        # Limita a 10: a lista pode ter uma entrada por registro do lote.
        linhas.extend(f"• {e}" for e in erros[:10])
        if len(erros) > 10:
            linhas.append(f"• (+{len(erros) - 10} outros)")
    elif aceitos_bruto is not None and aceitos < enviados:
        # Sem isto a mensagem parecia esconder o motivo; o ERP é que não informou.
        linhas.append(
            f"O ERP não informou quais dos {enviados - aceitos} registros recusou "
            "(resposta completa no histórico)."
        )
    detalhe = str(body.get("errorMessage") or body.get("message") or "").strip()
    linhas.append(f"Resposta do ERP: HTTP {status}{f' — {detalhe}' if detalhe else ''}")
    return {
        "ok": False,
        "aceitos": aceitos,
        "mensagem": "\n".join(linhas) or "Falha ao incluir a coparticipação.",
    }


def _recusas(body: dict) -> dict[int, str]:
    """
    Posição (1-based) -> motivo, das chaves "item_N" da resposta do ERP.

    Vazio significa duas coisas MUITO diferentes: nada falhou, ou o ERP não disse
    quais falharam — quem chama compara com a contagem (`totalOk`) para saber.
    """
    bruto = body.get("errors")
    itens: list[Any] = []
    if isinstance(bruto, list):
        itens = bruto
    elif isinstance(bruto, dict):
        for valor in bruto.values():
            if isinstance(valor, list):
                itens.extend(valor)
    recusas: dict[int, str] = {}
    for e in itens:
        if isinstance(e, dict):
            for chave, valor in e.items():
                achado = _RE_ITEM.match(str(chave))
                if achado:
                    motivo = _motivo_do_erro(valor) if isinstance(valor, dict) else str(valor)
                    recusas[int(achado.group(1))] = motivo
    return recusas


def _itens_por_empresa(itens: list[dict]) -> dict[str, list[dict]]:
    """Agrupa os itens do snapshot por empresa (rótulo cru, para achar o rest)."""
    grupos: dict[str, list[dict]] = defaultdict(list)
    for item in itens:
        empresa = str(item.get("empresa") or "").strip()
        if empresa:
            grupos[empresa].append(item)
    return dict(grupos)


async def enviar_coparticipacao(
    settings: Settings,
    cfg: ConfigFiscal,
    tipo: str,
    resultado: dict,
    competencia_pagamento: str,
    ja_enviadas: set[str] | None = None,
    pendentes_por_empresa: dict[str, list[str]] | None = None,
) -> dict:
    """
    Inclui o desconto de coparticipação na folha, POR EMPRESA (um POST em lote).

    `competencia_pagamento` (AAAAMM) é informada no envio — é a competência da
    FOLHA em que o desconto entra, não a dos eventos (que é a da execução).
    `ja_enviadas` = empresas já enviadas (reenvio pula) — a proteção que evita
    descontar duas vezes do mesmo colaborador.

    `pendentes_por_empresa` = matrículas que o ERP recusou num envio anterior.
    Quando informado para uma empresa, o lote leva SOMENTE essas matrículas: as que
    ele já aceitou não voltam (seriam duplicidade na folha). Empresa marcada como
    parcial SEM lista identificada não é reenviada automaticamente — reenviar tudo
    arriscaria dobrar o desconto de quem já entrou.

    Sem trava anti-parcial entre empresas (ao contrário da AE): cada empresa é uma
    folha independente, e uma falha na Vertex não é razão para deixar a
    Zenith sem desconto. O que uma empresa recusou fica no seu `mensagem`.

    Retorna o mesmo formato de `enviar_rateio` — `contrato` e `titulo` vazios,
    porque esta rotina não gera nenhum dos dois.
    """
    ja_enviadas = ja_enviadas or set()
    pendentes_por_empresa = pendentes_por_empresa or {}
    modulo = _modulo_de(tipo)
    data_ocorrencia = _emissao_hoje()

    grupos = _itens_por_empresa(resultado.get("itens") or [])
    pendentes = {e: itens for e, itens in grupos.items() if e not in ja_enviadas}

    alertas: list[str] = []
    envios: list[dict] = []
    for empresa, itens in pendentes.items():
        rest = cfg.rest_da_empresa(empresa)
        # Reenvio seletivo: só as matrículas recusadas antes (se conhecidas).
        alvo = pendentes_por_empresa.get(empresa)
        matriculas = set(alvo) if alvo else None
        payload = modulo.gerar_payload_erp(
            itens, competencia_pagamento, data_ocorrencia, empresa, matriculas
        )
        if not payload:
            # Todos em tratativa manual (PJ, teto atingido), sem matrícula ou com
            # valor zerado. Não é erro — mas também não é "enviado", senão a
            # empresa sairia do reenvio sem nunca ter sido lançada.
            alertas.append(
                f"Empresa '{empresa}': nenhum colaborador elegível ao lançamento "
                f"(PJ, teto atingido, sem matrícula ou valor zerado); nenhum registro foi enviado."
            )
            continue
        if not rest:
            envios.append({"empresa": empresa, "rest": "", "contrato": "", "titulo": "",
                           "status": "erro", "mensagem": f"Empresa '{empresa}' sem rest mapeado no Protheus."})
            continue
        # Posição no lote -> pessoa/matrícula: é assim que o ERP identifica o
        # registro recusado ("item_26"); sem a tradução o erro fica ilegível e não
        # há como reenviar só os que falharam.
        nome_por_matricula = {
            str(i.get("matricula") or ""): str(i.get("nome") or "") for i in itens
        }
        matricula_por_posicao = {
            pos: entrada["HEADER"]["RA_MAT"] for pos, entrada in enumerate(payload, start=1)
        }
        rotulos = {
            pos: f"{nome_por_matricula.get(mat, '')} (mat {mat})".strip()
            for pos, mat in matricula_por_posicao.items()
        }
        reenvio = matriculas is not None

        resp: dict | None = None
        try:
            resp = await protheus.incluir_coparticipacao(settings, rest, payload)
            res = _interpretar_resposta_copart(resp, len(payload), rotulos)
        except protheus.ProtheusError as exc:
            res = {"ok": False, "aceitos": 0, "mensagem": f"Falha de comunicação com o ERP: {exc}"}
        if not res["ok"]:
            # Falha (inclusive 200 parcial): o corpo bruto é a única fonte de QUAIS
            # registros o ERP recusou. Vai para o log e para o histórico.
            logger.warning(
                "Coparticipação %s (%s): %s | resposta do ERP: %s",
                empresa, rest, res["mensagem"], resp,
            )

        corpo = resp.get("body") if isinstance(resp, dict) else None
        # Pendências ESTRUTURADAS: a UI monta a apresentação a partir daqui, em vez
        # de reimprimir a mensagem técnica do ERP.
        recusadas = [
            {
                "matricula": matricula_por_posicao[pos],
                "nome": nome_por_matricula.get(matricula_por_posicao[pos], ""),
                "motivo": motivo,
            }
            for pos, motivo in sorted(_recusas(corpo or {}).items())
            if pos in matricula_por_posicao
        ]
        aceitos = res.get("aceitos", 0)
        enviados = len(payload)

        if res["ok"]:
            status = "enviado"
            mensagem = (
                f"{aceitos} matrícula(s) pendente(s) incluída(s); envio concluído."
                if reenvio
                else res["mensagem"]
            )
        elif aceitos > 0:
            # Parte entrou na folha: NÃO é erro nem sucesso. As aceitas não podem
            # voltar num reenvio, então o que importa é a lista das recusadas.
            status = "parcial"
            mensagem = res["mensagem"]
        else:
            status = "erro"
            mensagem = res["mensagem"]

        envio = {
            "empresa": empresa, "rest": rest, "contrato": "", "titulo": "",
            "status": status, "mensagem": mensagem,
            "enviados": enviados, "aceitos": aceitos,
            "resposta": resp,
        }
        if resp is not None:
            # Recusadas conhecidas; no reenvio, quem não voltou a falhar saiu da
            # pendência. Vazio com aceitos<enviados = o ERP não identificou.
            envio["matriculas_pendentes"] = recusadas
        elif matriculas:
            # Falha de COMUNICAÇÃO num reenvio seletivo: não sabemos o que o ERP
            # fez, mas o alvo continua sendo o mesmo. Zerar a lista faria o próximo
            # reenvio mandar a empresa inteira e duplicar quem já entrou.
            envio["matriculas_pendentes"] = [
                {"matricula": m, "nome": nome_por_matricula.get(m, ""),
                 "motivo": "Não confirmado pelo ERP (falha de comunicação)."}
                for m in sorted(matriculas)
            ]
        envios.append(envio)

    return {"bloqueado": False, "bloqueios": [], "alertas": alertas, "envios": envios}


# --- Telefonia (AE por BOLETO sobre contrato de parceria) -------------------
# Mesma rotina do plano de saúde (contrato -> AE -> título), com duas diferenças:
# todos os boletos vão para UMA empresa, e cada boleto vira UM título. Por isso a
# unidade de envio é o boleto (referência = conta da Claro), não a empresa.
# O que compõe cada título é regra do módulo (`titulos_erp`); aqui fica contrato,
# casamento CC -> item, POST e interpretação da resposta.


async def enviar_titulos_por_referencia(
    settings: Settings,
    cfg: ConfigFiscal,
    tipo: str,
    resultado: dict,
    empresa: str,
    ja_enviadas: set[tuple[str, str]] | None = None,
    on_evento: Callable[[dict], None] | None = None,
) -> dict:
    """
    Lança uma Autorização de Entrega por TÍTULO declarado pelo módulo.

    `ja_enviadas` = (empresa, referência) já integradas — o reenvio pula essas,
    para não gerar título em dobro para o mesmo documento.

    `on_evento` é chamado ANTES de cada POST ({"fase": "enviando", ...}) e depois
    da resposta ({"fase": "concluido", ...com o envio}). É por ele que o chamador
    grava cada título assim que ele entra, em vez de esperar o lote inteiro: numa
    queda no meio (timeout, rede, reinício) o que já foi lançado fica registrado,
    e o reenvio não duplica. O serviço segue sem tocar banco.

    TRAVA ANTI-PARCIAL (decisão do negócio): valida TODOS os títulos pendentes
    antes de postar qualquer um. Bloqueio do módulo (ex.: linha cobrada sem centro
    de custo/classe), contrato ausente ou centro de custo fora do contrato impedem
    o envio inteiro — lançar 7 de 8 é envio parcial, e a notificação ao fiscal só
    sai quando todos entraram. A quantidade é a dos documentos recebidos: 1, 2 ou N.
    """
    ja_enviadas = ja_enviadas or set()
    rest = cfg.rest_da_empresa(empresa)
    cnpj = _cnpj_fornecedor(settings, cfg, _operadora_do_tipo(tipo))
    modulo = _modulo_de(tipo)

    bloqueios: list[str] = list(resultado.get("bloqueios") or [])
    alertas: list[str] = []
    envios: list[dict] = []

    titulos = [
        t for t in modulo.titulos_erp(resultado)
        if (empresa, t["referencia"]) not in ja_enviadas
    ]
    if not titulos:
        return {
            "bloqueado": False, "bloqueios": [], "envios": [],
            "alertas": ["Nenhum documento pendente de lançamento."],
        }
    if not rest:
        bloqueios.append(f"Empresa '{empresa}' sem rest mapeado no Protheus.")
    if not cnpj:
        bloqueios.append(f"CNPJ do fornecedor ({_operadora_do_tipo(tipo)}) não cadastrado.")

    contrato = None
    if not bloqueios:
        try:
            # `rest` já foi validado acima (bloqueio "sem rest mapeado"), então
            # aqui ele nunca é None; o mypy não acompanha a trava.
            contratos = _agrupar_por_numero(
                await protheus.buscar_contratos(settings, rest, cnpj)  # type: ignore[arg-type]
            )
        except protheus.ProtheusError as exc:
            contratos = []
            bloqueios.append(f"Falha ao buscar o contrato de parceria ({exc}).")
        if not bloqueios:
            # Um contrato para todos os títulos: a cobertura exigida é a união dos
            # centros de custo de todos eles.
            ccs = {
                str(linha["centro_custo"]).strip()
                for t in titulos for linha in t["linhas"]
            }
            contrato = _escolher_contrato(contratos, ccs)
            if contrato is None:
                bloqueios.append(
                    f"Não há contrato de parceria disponível para a empresa {empresa}. "
                    "Crie o contrato no ERP antes de lançar."
                )

    # Prepara TODOS antes de postar QUALQUER um (anti-parcial).
    preparados: list[dict] = []
    if contrato is not None:
        numero_contrato = str((contrato.get("HEADER") or {}).get("C3_NUM", ""))
        for titulo in titulos:
            referencia = titulo["referencia"]
            linhas = [
                {
                    "centro_custo": l["centro_custo"],
                    "classe_valor": l["classe_valor"],
                    "valor": Decimal(str(l["valor"])),
                }
                for l in titulo["linhas"]
            ]
            if not linhas:
                bloqueios.append(f"Documento {referencia}: nenhum item por centro de custo.")
                continue
            # O produto de cada item vem do ITEM DO CONTRATO (a telefonia já usa
            # 400178 lá), então não há divergência a validar no ERP.
            payload, faltantes = _montar_payload(contrato, linhas, titulo["observacao"], cnpj)
            if faltantes:
                bloqueios.append(
                    f"Documento {referencia}: centro(s) de custo fora do contrato "
                    f"{numero_contrato} — inclua-os no contrato no ERP antes de lançar: "
                    + ", ".join(sorted(set(faltantes))) + "."
                )
                continue
            preparados.append({
                "referencia": referencia,
                "contrato_num": numero_contrato,
                "payload": payload,
            })

    if bloqueios:
        return {"bloqueado": True, "bloqueios": bloqueios, "alertas": alertas, "envios": []}

    for prep in preparados:
        if on_evento:
            on_evento({
                "fase": "enviando", "empresa": empresa, "referencia": prep["referencia"],
                "rest": rest, "contrato": prep["contrato_num"],
            })
        try:
            resp = await protheus.incluir_autorizacao_entrega(
                settings, rest, prep["payload"]  # type: ignore[arg-type]  # ver acima
            )
            res = _interpretar_resposta(resp)
        except protheus.ProtheusError as exc:
            resp = None
            res = {"ok": False, "titulo": "", "mensagem": f"Falha de comunicação com o ERP: {exc}"}
        if not res["ok"]:
            logger.warning(
                "AE %s (ref %s): %s | HEADER enviado: %s | %d item(ns) | resposta do ERP: %s",
                empresa, prep["referencia"], res["mensagem"],
                prep["payload"].get("HEADER"), len(prep["payload"].get("ITENS") or []), resp,
            )
        envio = {
            "empresa": empresa, "referencia": prep["referencia"], "rest": rest,
            "contrato": prep["contrato_num"], "titulo": res["titulo"],
            "status": "enviado" if res["ok"] else "erro", "mensagem": res["mensagem"],
            "resposta": resp,
        }
        envios.append(envio)
        if on_evento:
            on_evento({"fase": "concluido", **envio})

    return {"bloqueado": False, "bloqueios": [], "alertas": alertas, "envios": envios}
