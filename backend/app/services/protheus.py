"""
Cliente da API Protheus.

Responsabilidades:
- `listar_colaboradores`: busca colaboradores + dependentes de TODAS as empresas
  do grupo. Cada empresa é um "rest" diferente na URL (concatenada como
  {base}/{rest}/{path}); o resultado de cada rest é marcado com a `empresa`
  correspondente e concatenado numa lista única — exatamente o formato que o
  `calculator` do módulo espera em `dados_externos["colaboradores"]`.
- `buscar_contratos` / `incluir_autorizacao_entrega` / `incluir_pre_nota`:
  contratos de parceria e as inclusões que geram título no ERP.

DUAS BASES, separadas por EIXO (leitura x escrita), não por ambiente:
- LEITURA (`protheus_read_*`): consultas de cadastro — hoje na base OFICIAL.
- ESCRITA (`protheus_write_*`): toda inclusão — hoje na base de TESTE. O GET de
  contratos usa a base de ESCRITA de propósito (a AE referencia um contrato que
  precisa existir onde o título será gravado).
Cada função declara sua base; nada aqui consulta "estou em teste?". Trocar de
ambiente é `.env` (ver `app/config.py`).

Esta é a camada de infraestrutura: o router a chama para montar `dados_externos`
e mantém os módulos de rateio puros. Autenticação por token Bearer (se
configurado) ou basic (user/senha), com credenciais por base.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

# Situações consideradas INATIVAS (colaborador desligado). Comparadas já
# normalizadas (maiúsculas, sem acento). Ajuste se o Protheus usar outros termos.
SITUACOES_INATIVAS: set[str] = {"DEMITIDO"}


class ProtheusError(RuntimeError):
    """Falha ao comunicar com a API Protheus."""


def _norm(texto: Any) -> str:
    if texto is None:
        return ""
    forma = unicodedata.normalize("NFKD", str(texto)).upper()
    return "".join(c for c in forma if not unicodedata.combining(c)).strip()


def _cpf_digitos(valor: Any) -> str:
    """CPF só com dígitos, com zero à esquerda até 11 (chave de dedup)."""
    digitos = re.sub(r"\D", "", str(valor or ""))
    return digitos.zfill(11) if 0 < len(digitos) <= 11 else digitos


def colaborador_ativo(colaborador: dict[str, Any]) -> bool:
    """True se a `situacao` não estiver na lista de inativas."""
    return _norm(colaborador.get("situacao")) not in SITUACOES_INATIVAS


def _salario(colaborador: dict[str, Any]) -> Decimal:
    """Salário como Decimal (0 se ausente/zerado/inválido) — chave de desempate."""
    valor = colaborador.get("salario", 0)
    if isinstance(valor, Decimal):
        return valor
    try:
        return Decimal(str(valor).strip().replace(",", ".") or "0")
    except (InvalidOperation, ValueError):
        return Decimal(0)


def _preferencia(colaborador: dict[str, Any]) -> tuple[bool, Decimal]:
    """
    Chave de preferência ao deduplicar o mesmo CPF (maior vence).

    1) ATIVO vence INATIVO — sempre; nunca escolhemos um desligado, mesmo que
       tenha salário maior (o custo vai para onde a pessoa está hoje).
    2) Empatando na situação, vence o MAIOR salário — resolve o caso da API que
       devolve o colaborador com salário zerado em uma empresa e correto em outra.
    """
    return (colaborador_ativo(colaborador), _salario(colaborador))


def _url_leitura(settings: Settings, rest: str) -> str:
    """URL de CONSULTA (base de leitura): {base}/{rest}/{path}."""
    base = settings.protheus_read_base_url.rstrip("/")
    path = settings.protheus_colaboradores_path.strip("/")
    return f"{base}/{rest}/{path}"


def _credenciais(settings: Settings, escrita: bool) -> tuple[str, str, str]:
    """(user, senha, token) da base alvo. A escrita herda a leitura se não tiver as suas."""
    if escrita:
        return settings.credenciais_escrita()
    return (settings.protheus_user, settings.protheus_password, settings.protheus_token)


def _auth_headers(settings: Settings, escrita: bool = False) -> dict[str, str]:
    _, _, token = _credenciais(settings, escrita)
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _basic_auth(settings: Settings, escrita: bool = False) -> httpx.BasicAuth | None:
    user, senha, token = _credenciais(settings, escrita)
    if not token and user:
        return httpx.BasicAuth(user, senha)
    return None


async def _buscar_rest(
    client: httpx.AsyncClient,
    settings: Settings,
    rest: str,
    incluir_desligados: bool,
) -> list[dict[str, Any]]:
    """Busca todos os colaboradores de um rest, seguindo a paginação."""
    url = _url_leitura(settings, rest)
    colaboradores: list[dict[str, Any]] = []
    pagina = 1
    while True:
        try:
            resposta = await client.get(
                url,
                params={
                    "nPage": pagina,
                    "cListDes": "S" if incluir_desligados else "N",
                },
                headers=_auth_headers(settings),
                auth=_basic_auth(settings),
            )
            resposta.raise_for_status()
            dados = resposta.json()
        except httpx.HTTPError as exc:
            raise ProtheusError(f"Erro ao consultar {url} (página {pagina}): {exc}") from exc

        colaboradores.extend(dados.get("colaboradores", []) or [])

        meta = dados.get("meta") or {}
        total_paginas = int(meta.get("total_page", 1) or 1)
        if pagina >= total_paginas:
            break
        pagina += 1

    return colaboradores


CHAVE_AMBIGUIDADE = "_ambiguidade"


def _rotulo_registro(colaborador: dict[str, Any]) -> str:
    """'Empresa/matrícula' — identifica o registro nos avisos ao usuário."""
    empresa = str(colaborador.get("empresa") or "?").strip()
    matricula = str(colaborador.get("matricula") or "?").strip()
    return f"{empresa}/{matricula}"


def resolver_duplicados(colaboradores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Deduplica colaboradores por CPF, mantendo o registro preferível.

    Um mesmo CPF pode aparecer em mais de um rest (ex.: transferência no grupo,
    Vertex -> Zenith: demitido na rest02, ativo na rest15). Regra de negócio:
    **o registro não-demitido vence** — é dele que sai o salário (logo, a faixa) e
    é a MESMA empresa/matrícula/filial que vai ao lançamento no ERP. Sem isso o
    desconto entraria na folha de uma empresa onde a pessoa não está mais.

    Critério de preferência (ao colidir o CPF), ver `_preferencia`: ativo >
    inativo; empatando na situação, vence o MAIOR salário (resolve a API que
    devolve o mesmo colaborador zerado numa empresa e correto em outra).

    EMPATE no topo do critério (ex.: ativo com o mesmo salário em duas empresas)
    só é ambíguo quando os empatados DIVERGEM em empresa/matrícula: aí a escolha é
    indecidível, o registro recebe `CHAVE_AMBIGUIDADE` e o rateio avisa e deixa a
    pessoa fora do lançamento automático — errar a empresa desconta na folha
    errada. Empatados que apontam para a MESMA empresa/matrícula são o mesmo
    destino (a API repete o registro): escolhe qualquer um, sem marcar nada.
    Registros sem CPF não são deduplicados (mantidos como estão).
    """
    candidatos: dict[str, list[dict[str, Any]]] = {}
    sem_cpf: list[dict[str, Any]] = []
    for colaborador in colaboradores:
        cpf = _cpf_digitos(colaborador.get("cpf"))
        if not cpf:
            sem_cpf.append(colaborador)
            continue
        candidatos.setdefault(cpf, []).append(colaborador)

    resultado: list[dict[str, Any]] = []
    for cpf, registros in candidatos.items():
        topo = max(_preferencia(r) for r in registros)
        empatados = [r for r in registros if _preferencia(r) == topo]
        escolhido = empatados[0]
        # Só é ambíguo se os empatados levarem a destinos DIFERENTES na folha.
        # E só importa em quem está ATIVO: demitido não vira item de rateio (o
        # cálculo o manda para divergência), então marcá-lo seria ruído.
        destinos = sorted({_rotulo_registro(r) for r in empatados})
        if len(destinos) > 1 and colaborador_ativo(escolhido):
            escolhido[CHAVE_AMBIGUIDADE] = destinos
            logger.warning(
                "CPF %s tem registros equivalentes em destinos diferentes (%s) — "
                "escolhido %s; fora do lançamento automático (tratativa manual).",
                cpf, ", ".join(destinos), _rotulo_registro(escolhido),
            )
        resultado.append(escolhido)
    return resultado + sem_cpf


async def listar_colaboradores(
    settings: Settings,
    client: httpx.AsyncClient | None = None,
    incluir_desligados: bool = True,
    rests: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """
    Busca colaboradores + dependentes de todas as empresas (rests) do grupo.

    Cada colaborador retornado ganha a chave `empresa` conforme o mapa
    `settings.protheus_rests`. Com `incluir_desligados=True` (cListDes=S) a API
    também traz demitidos que ainda possam estar no detalhamento das operadoras;
    por isso o resultado é DEDUPLICADO por CPF (ver `resolver_duplicados`).

    Args:
        settings: configurações (URLs, credenciais, rests).
        client: cliente httpx opcional (para reuso/testes); se ausente, um é
            criado e fechado internamente.
        incluir_desligados: envia cListDes=S para incluir colaboradores demitidos.
    """
    proprio = client is None
    cli = client or httpx.AsyncClient(
        timeout=settings.protheus_read_timeout,
        verify=settings.protheus_read_verify_ssl,
    )
    try:
        rests_alvo = rests if rests is not None else settings.protheus_rests
        resultado: list[dict[str, Any]] = []
        for rest, empresa in rests_alvo.items():
            for colaborador in await _buscar_rest(cli, settings, rest, incluir_desligados):
                colaborador["empresa"] = empresa
                resultado.append(colaborador)
        return resolver_duplicados(resultado)
    finally:
        if proprio:
            await cli.aclose()


def _url_escrita(settings: Settings, rest: str, path: str) -> str:
    """
    URL da base de ESCRITA: {base}/{rest}/{path}.

    Também é usada pelo GET de contratos: a AE referencia o C3_NUM do contrato,
    que precisa existir na mesma base onde o título será gravado.
    """
    base = settings.protheus_write_base_url.rstrip("/")
    if not base:
        raise ProtheusError(
            "PROTHEUS_WRITE_BASE_URL não configurada — nenhuma inclusão no ERP é "
            "possível. Defina a base de escrita no .env."
        )
    return f"{base}/{rest}/{path.lstrip('/')}"


def _cliente_escrita(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=settings.protheus_write_timeout,
        verify=settings.protheus_write_verify_ssl,
    )


async def buscar_contratos(
    settings: Settings,
    rest: str,
    cnpj_fornecedor: str,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """
    GET dos Contratos de Parceria DISPONÍVEIS do fornecedor (`cCGCFornecedor`)
    na empresa do `rest`. Cada item traz HEADER (inclui C3_NUM = nº do contrato)
    e ITEMS (com C3_CC, C3_CLVL, C3_PRODUTO, C3_LOCAL, C3_ITEM). O endpoint só
    devolve contratos disponíveis — lista vazia = nenhum contrato para a empresa.
    """
    url = _url_escrita(settings, rest, settings.protheus_contratos_path)
    proprio = client is None
    cli = client or _cliente_escrita(settings)
    try:
        items: list[dict[str, Any]] = []
        pagina = 1
        while True:
            try:
                resposta = await cli.get(
                    url,
                    params={"cCGCFornecedor": cnpj_fornecedor, "nPage": pagina},
                    headers=_auth_headers(settings, escrita=True),
                    auth=_basic_auth(settings, escrita=True) or httpx.USE_CLIENT_DEFAULT,
                )
                resposta.raise_for_status()
                dados = resposta.json()
            except httpx.HTTPError as exc:
                raise ProtheusError(f"Erro ao consultar contratos ({url}): {exc}") from exc
            items.extend(dados.get("items", []) or [])
            meta = dados.get("metaData") or {}
            total_paginas = int(meta.get("nTotalPages", 1) or 1)
            if pagina >= total_paginas:
                break
            pagina += 1
        return items
    finally:
        if proprio:
            await cli.aclose()


async def _post_erp(
    settings: Settings,
    rest: str,
    path: str,
    payload: dict[str, Any] | list[dict[str, Any]],
    rotulo: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """
    POST genérico na base de ESCRITA. NÃO usa raise_for_status: o ERP responde 4xx
    com corpo JSON de erro que precisamos preservar. Retorna {http_status, body}
    para o chamador interpretar sucesso/erro.

    Toda inclusão registra no log a URL-alvo e o ambiente: é o rastro que responde
    "onde este título foi gravado?" sem depender de ninguém lembrar do .env.
    """
    # A coerência da configuração de escrita é cobrada AQUI, não na subida: um
    # `.env` incoerente deve impedir a gravação no ERP, não o login de todos.
    problemas = settings.problemas_escrita()
    if problemas:
        raise ProtheusError(
            "Configuração de escrita no ERP inconsistente — inclusão bloqueada: "
            + " ".join(problemas)
        )
    url = _url_escrita(settings, rest, path)
    logger.info(
        "ERP[%s] POST %s (%s)", settings.protheus_write_ambiente.upper(), url, rotulo
    )
    proprio = client is None
    cli = client or _cliente_escrita(settings)
    try:
        try:
            resposta = await cli.post(
                url,
                json=payload,
                headers={
                    **_auth_headers(settings, escrita=True),
                    "Content-Type": "application/json",
                },
                auth=_basic_auth(settings, escrita=True) or httpx.USE_CLIENT_DEFAULT,
            )
        except httpx.HTTPError as exc:
            raise ProtheusError(f"Erro ao incluir {rotulo} ({url}): {type(exc).__name__}: {exc}") from exc
        try:
            body = resposta.json()
        except ValueError:
            body = {"raw": resposta.text}
        return {"http_status": resposta.status_code, "body": body}
    finally:
        if proprio:
            await cli.aclose()


async def incluir_autorizacao_entrega(
    settings: Settings, rest: str, payload: dict[str, Any],
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """POST da Autorização de Entrega (gera o título) na empresa do `rest`."""
    return await _post_erp(settings, rest, settings.protheus_ae_path, payload, "AE", client)


async def incluir_pre_nota(
    settings: Settings, rest: str, payload: dict[str, Any],
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """POST da pré-nota (entrada de nota) na empresa do `rest` (ex.: Zenith)."""
    return await _post_erp(settings, rest, settings.protheus_prenota_path, payload, "pré-nota", client)


async def incluir_coparticipacao(
    settings: Settings, rest: str, payload: list[dict[str, Any]],
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """
    POST do desconto de coparticipação na folha, na empresa do `rest`.

    O payload é um LOTE: uma entrada por matrícula ({HEADER, ITENS}). Não gera
    título — inclui o desconto na folha. A resposta traz `totalOk` e a lista de
    erros por registro (ver `erp._interpretar_resposta_copart`).
    """
    return await _post_erp(
        settings, rest, settings.protheus_coparticipacao_path, payload, "coparticipação", client
    )
