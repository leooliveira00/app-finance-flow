"""
Rotas HTTP da plataforma de rateio.

Este router é genérico: ele aciona qualquer módulo registrado a partir do
`tipo` informado na URL, sem conhecer os detalhes de cada rateio. Toda a
lógica vive nos módulos (app/modules/); aqui só há orquestração HTTP e a
serialização do resultado (JSON de resumo e CSV de download).

O prefixo "/api" é aplicado em main.py ao incluir este router.

--- ESPECIFICAÇÃO DO CSV DE SAÍDA ---
Colunas fixas (nesta ordem): cpf; nome; departamento; centro_de_custo;
valor_total; historico — seguidas das colunas de `ItemRateio.extras`
(específicas de cada rateio), em ordem alfabética das chaves.
Encoding: UTF-8 com BOM (utf-8-sig). Separador: ponto e vírgula (";").
"""

import csv
import io
import re
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import service as auth_service
from app.auth.deps import usuario_atual
from app.auth.redacao import CAMPOS_AUDITORIA, redigir_resultado
from app.config import Settings, get_settings
from app.db.session import get_db
from app.modules.base import ItemRateio
from app.modules.registry import registry
from app.services import organizacao, organizacao_fiscal, processos, protheus
from app.services.cadastro import (
    carregar_colaboradores_demo,
    carregar_consenso,
    carregar_linhas_telefonicas,
    carregar_parametros_telefonia,
    carregar_pj,
)
from app.version import __version__

router = APIRouter()


# --- Constantes da especificação do CSV de saída ---
CSV_COLUNAS: list[str] = [
    "cpf",
    "nome",
    "departamento",
    "centro_de_custo",
    "valor_total",
    "historico",
]
CSV_ENCODING: str = "utf-8-sig"
CSV_SEPARADOR: str = ";"

# CSV dos colaboradores PJ: eles NÃO vão no lançamento em folha (não têm
# matrícula/filial no Protheus) — o desconto é cobrado na nota, num processo
# manual. Este CSV é o apoio a esse processo.
CSV_PJ_COLUNAS: list[str] = ["nome", "cpf", "operadora", "valor_a_descontar"]
OPERADORA_LABEL: dict[str, str] = {"unimed": "Unimed", "bradesco": "Bradesco"}

# Último processamento em memória, guardado para servir CSV/TXT de download.
# Chave (email_do_usuário, tipo): isola usuários — dois operadores processando o
# MESMO rateio não sobrescrevem o resultado um do outro. (Ainda é por processo:
# com múltiplos workers/réplicas, use sessão presa ou um store compartilhado.)
_ULTIMO_RESULTADO: dict[tuple[str, str], list[ItemRateio]] = {}


def _chave_resultado(usuario: dict, tipo: str) -> tuple[str, str]:
    return (str(usuario.get("email", "")), tipo)


@router.get("/health")
def health() -> dict[str, str]:
    """
    Healthcheck simples da API (readiness/liveness).

    Devolve também a versão do build: é como se confere qual release está no ar
    num host de produção sem abrir o container (a versão é mantida pelo
    semantic-release em `app/version.py`).
    """
    return {"status": "ok", "versao": __version__}


@router.get("/modulos")
def listar_modulos(
    incluir_inativos: bool = False,
    usuario: dict = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> list[dict[str, str]]:
    """
    Lista os módulos de rateio VISÍVEIS ao usuário ({tipo, nome, descricao, area}).

    Dois filtros: a segregação por ÁREA (o usuário só recebe os rateios das
    áreas às quais pertence, ou todos, se admin) e a DISPONIBILIDADE do processo
    (inativo sai do painel — ver `models/processo.py`).

    `incluir_inativos` é honrado só para admin: as telas de Configurações
    precisam enxergar o processo desativado, porque é nelas que se termina o
    cadastro que falta para reativá-lo.
    """
    area_map = organizacao.mapa_areas_rateios(db)
    permitidos = auth_service.tipos_permitidos(usuario["areas"], area_map)
    # Admin é quem tem a área "*" — e é exatamente quem `tipos_permitidos`
    # devolve None. Reusar isso evita uma segunda definição de "é admin".
    ocultos: set[str] = set()
    if not (incluir_inativos and permitidos is None):
        ocultos = processos.tipos_inativos(db)
    return [
        {
            "tipo": modulo.tipo,
            "nome": getattr(modulo, "nome", "") or modulo.tipo.replace("-", " ").replace("_", " ").title(),
            "descricao": modulo.descricao,
            "area": auth_service.area_de_tipo(modulo.tipo, area_map) or "",
        }
        for modulo in registry.list_modules()
        if (permitidos is None or modulo.tipo in permitidos) and modulo.tipo not in ocultos
    ]


def _obter_modulo(tipo: str):
    try:
        return registry.get(tipo)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Rateio '{tipo}' não encontrado.") from exc


def _exigir_acesso(usuario: dict, tipo: str, area_map: dict[str, list[str]]) -> None:
    """403 se o usuário não puder acessar o rateio `tipo` (segregação por área)."""
    if not auth_service.pode_ver(usuario["areas"], tipo, area_map):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Sem permissão para o rateio '{tipo}'.",
        )


def _serializar_decimais(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, dict):
        return {k: _serializar_decimais(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_serializar_decimais(v) for v in valor]
    return valor


@router.post("/rateio/{tipo}/processar")
async def processar_rateio(
    tipo: str,
    arquivos: list[UploadFile] = File(...),
    settings: Settings = Depends(get_settings),
    usuario: dict = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Processa um rateio do `tipo` informado a partir dos arquivos enviados.

    Fluxo: valida acesso (403) -> obtém o módulo (404) -> busca colaboradores no
    Protheus, ou no cadastro fictício se o ERP não estiver configurado
    (dados_externos) -> valida a estrutura (422) -> processa -> guarda o
    resultado para o CSV -> devolve o resumo.
    """
    area_map = organizacao.mapa_areas_rateios(db)
    _exigir_acesso(usuario, tipo, area_map)
    modulo = _obter_modulo(tipo)
    # Processo inativo não inicia execução. A trava é aqui, e não só no painel:
    # uma aba aberta antes da desativação continuaria processando.
    if not processos.esta_ativo(db, tipo):
        raise HTTPException(
            status_code=409,
            detail=(
                "Este processo está inativo e não aceita novas execuções. "
                "O histórico segue disponível para consulta."
            ),
        )

    entrada = {f.filename: await f.read() for f in arquivos}

    # Rateios que não casam por pessoa (ex.: telefonia, por número de linha) não
    # consultam o Protheus — nem ficam indisponíveis quando ele está fora.
    colaboradores: list[dict[str, Any]] = []
    if getattr(modulo, "usa_colaboradores", True):
        if not settings.protheus_read_base_url:
            # ERP nunca configurado (instalação de demonstração pública): usa o
            # cadastro fictício em vez de chamar o Protheus. Só entra aqui pela
            # AUSÊNCIA da URL — uma falha de rede com o ERP já configurado
            # continua sendo erro (abaixo), nunca cai para dado fictício.
            colaboradores = carregar_colaboradores_demo(db)
        else:
            try:
                # Rests podem variar por rateio (ex.: Unimed só Vertex+Zenith).
                # Empresas/rests vêm do banco (cadastro); o filtro por tipo fica no config.
                cfg_fiscal = organizacao_fiscal.carregar_config_fiscal(db)
                colaboradores = await protheus.listar_colaboradores(
                    settings, rests=cfg_fiscal.rests_do_tipo(tipo, settings.protheus_rests_por_tipo)
                )
            except protheus.ProtheusError as exc:
                raise HTTPException(status_code=502, detail=f"Falha na API Protheus: {exc}") from exc
    # Cadastros do Postgres: cada módulo usa o que lhe interessa e ignora o resto
    # (consenso/pj -> coparticipação; linhas_telefonicas -> telefonia).
    dados_externos = {
        "colaboradores": colaboradores,
        "consenso": carregar_consenso(db),
        "pj": carregar_pj(db),
        "linhas_telefonicas": carregar_linhas_telefonicas(db),
        "parametros_telefonia": carregar_parametros_telefonia(db),
    }

    validacao = modulo.validar_inputs(entrada, dados_externos)
    if not validacao.valido:
        raise HTTPException(
            status_code=422,
            detail={"erros": validacao.erros, "alertas": validacao.alertas},
        )

    # Módulos que expõem resultado rico (divergências/reconciliação) usam-no;
    # os demais caem no contrato base. (Transição até ResultadoRateio virar padrão.)
    if all(hasattr(modulo, m) for m in ("processar_completo", "resultado_para_itens", "resumo")):
        resultado = modulo.processar_completo(entrada, dados_externos)
        itens = modulo.resultado_para_itens(resultado)
        resumo = _serializar_decimais(modulo.resumo(resultado))
    else:
        itens = modulo.processar(entrada, dados_externos)
        resumo = {"itens": [_serializar_decimais(vars(i)) for i in itens]}

    _ULTIMO_RESULTADO[_chave_resultado(usuario, tipo)] = itens

    # Redige salário/teto para quem não é admin_area/admin da área do tipo.
    pode_auditar = auth_service.pode_auditar(
        usuario["areas"], usuario.get("niveis", {}), tipo, area_map
    )
    return {
        "tipo": tipo,
        "alertas_validacao": validacao.alertas,
        "total_itens": len(itens),
        # Sinaliza ao front se pode auditar (ver salário/teto) — esconde a opção
        # "Auditar" para o operador. A redação abaixo já garante a segurança.
        "pode_auditar": pode_auditar,
        "resultado": redigir_resultado(resumo, pode_auditar),
    }


@router.get("/rateio/{tipo}/resultado.csv")
def baixar_resultado_csv(
    tipo: str,
    usuario: dict = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Retorna o CSV do último processamento do rateio `tipo`."""
    area_map = organizacao.mapa_areas_rateios(db)
    _exigir_acesso(usuario, tipo, area_map)
    _obter_modulo(tipo)  # valida o tipo (404)
    itens = _ULTIMO_RESULTADO.get(_chave_resultado(usuario, tipo))
    if not itens:
        raise HTTPException(
            status_code=404,
            detail=f"Nenhum processamento prévio para o rateio '{tipo}'.",
        )

    # Redige salário/teto no CSV para quem não pode auditar (aplica-se por request,
    # pois _ULTIMO_RESULTADO é global por tipo e guarda o resultado completo).
    pode_auditar = auth_service.pode_auditar(
        usuario["areas"], usuario.get("niveis", {}), tipo, area_map
    )
    # Colunas de extras: união das chaves presentes, em ordem estável.
    chaves_extras = sorted({chave for item in itens for chave in item.extras})
    if not pode_auditar:
        chaves_extras = [c for c in chaves_extras if c not in CAMPOS_AUDITORIA]
    cabecalho = CSV_COLUNAS + chaves_extras

    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=CSV_SEPARADOR, lineterminator="\n")
    escritor.writerow(cabecalho)
    for item in itens:
        linha = [
            item.colaborador_cpf,
            item.colaborador_nome,
            item.departamento,
            item.centro_de_custo,
            str(item.valor),
            item.historico,
        ] + [item.extras.get(chave, "") for chave in chaves_extras]
        escritor.writerow(linha)

    conteudo = buffer.getvalue().encode(CSV_ENCODING)
    return StreamingResponse(
        io.BytesIO(conteudo),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="rateio_{tipo}.csv"'
        },
    )


@router.get("/rateio/{tipo}/pj.csv")
def baixar_pj_csv(
    tipo: str,
    usuario: dict = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """CSV dos colaboradores PJ (nome, CPF, operadora, valor a descontar).

    PJ não entra no lançamento em folha (sem matrícula/filial no Protheus): o
    desconto é cobrado na nota, e o colaborador envia o comprovante ao
    responsável. Este CSV apoia esse processo manual. Usa o último processamento
    do rateio (mesmo cache do CSV/TXT). Valor com vírgula decimal (Excel pt-BR).
    """
    area_map = organizacao.mapa_areas_rateios(db)
    _exigir_acesso(usuario, tipo, area_map)
    _obter_modulo(tipo)  # valida o tipo (404)
    itens = _ULTIMO_RESULTADO.get(_chave_resultado(usuario, tipo))
    if not itens:
        raise HTTPException(
            status_code=404,
            detail=f"Nenhum processamento prévio para o rateio '{tipo}'.",
        )

    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=CSV_SEPARADOR, lineterminator="\n")
    escritor.writerow(CSV_PJ_COLUNAS)
    total = Decimal("0")
    for item in itens:
        if item.extras.get("pj") != "sim" or item.valor <= 0:
            continue
        operadora = (item.extras.get("operadora", "") or "").lower()
        escritor.writerow([
            item.colaborador_nome,
            item.colaborador_cpf,
            OPERADORA_LABEL.get(operadora, operadora.title()),
            f"{item.valor:.2f}".replace(".", ","),
        ])
        total += item.valor
    # Linha de total: o responsável confere a soma do que será cobrado na nota.
    escritor.writerow(["TOTAL", "", "", f"{total:.2f}".replace(".", ",")])

    conteudo = buffer.getvalue().encode(CSV_ENCODING)
    return StreamingResponse(
        io.BytesIO(conteudo),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="pj_{tipo}.csv"'},
    )


@router.get("/rateio/{tipo}/resultado.txt")
def baixar_resultado_txt(
    tipo: str,
    competencia: str,
    empresa: str | None = None,
    usuario: dict = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """TXT de redundância p/ importação manual no ERP (fallback ao envio via API).

    `competencia` (query) é a competência de pagamento; normalizada para AAAAMM.
    `empresa` (query, opcional) filtra os colaboradores de uma única empresa
    (ex.: "Vertex", "Zenith"). Disponível apenas para módulos que implementam
    `gerar_txt_erp` (hoje só a coparticipação). Usa o último processamento do
    rateio (mesmo cache do CSV).
    """
    area_map = organizacao.mapa_areas_rateios(db)
    _exigir_acesso(usuario, tipo, area_map)
    modulo = _obter_modulo(tipo)
    if not hasattr(modulo, "gerar_txt_erp"):
        raise HTTPException(
            status_code=400,
            detail=f"Export TXT não disponível para o rateio '{tipo}'.",
        )

    comp = re.sub(r"\D", "", competencia or "")
    if len(comp) != 6:
        raise HTTPException(
            status_code=422,
            detail="Competência inválida — informe no formato AAAAMM (ex.: 202607).",
        )

    itens = _ULTIMO_RESULTADO.get(_chave_resultado(usuario, tipo))
    if not itens:
        raise HTTPException(
            status_code=404,
            detail=f"Nenhum processamento prévio para o rateio '{tipo}'.",
        )

    # Linha só com dígitos/ponto (sem acentos) — latin-1 basta e é seguro no ERP.
    conteudo = modulo.gerar_txt_erp(itens, comp, empresa).encode("latin-1", errors="replace")
    # Sufixo da empresa no nome do arquivo (só dígitos/letras, sem acento/espaço).
    sufixo_empresa = re.sub(r"[^A-Za-z0-9]+", "", empresa or "")
    nome_arquivo = (
        f"rateio_{tipo}_{sufixo_empresa}_{comp}.txt"
        if sufixo_empresa
        else f"rateio_{tipo}_{comp}.txt"
    )
    return StreamingResponse(
        io.BytesIO(conteudo),
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{nome_arquivo}"'
        },
    )
