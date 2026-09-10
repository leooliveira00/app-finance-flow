"""
Serviço de autenticação e autorização por área.

- Autenticação: a verificação usuário/senha vive em `app.services.organizacao`
  (lê do banco). Aqui ficam a EMISSÃO e a LEITURA do JWT.
- Autorização: resolve quais tipos de rateio um usuário pode ver, a partir das
  suas áreas (no token) e do mapa `área -> tipos`, passado pelo chamador (o
  router carrega o mapa do banco via `organizacao.mapa_areas_rateios`).

As áreas no token são nomes de área; o admin é representado por "*".
"""

from __future__ import annotations

import datetime as dt

import jwt

from app.config import get_settings


def criar_token(usuario: dict) -> str:
    """Emite um JWT com o usuário, suas áreas e o nível por área."""
    settings = get_settings()
    expira = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=settings.jwt_expira_min)
    payload = {
        "sub": usuario["email"],  # identidade = e-mail
        "nome": usuario["nome"],
        "areas": usuario["areas"],
        "niveis": usuario.get("niveis", {}),  # {nome_area: nivel}; vazio p/ admin
        "exp": expira,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algoritmo)


def usuario_do_token(token: str) -> dict:
    """Decodifica o JWT; lança jwt.PyJWTError se inválido/expirado."""
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algoritmo])
    return {
        "email": payload.get("sub"),
        "nome": payload.get("nome"),
        "areas": payload.get("areas", []),
        "niveis": payload.get("niveis", {}),
    }


def tipos_permitidos(areas: list[str], area_map: dict[str, list[str]]) -> set[str] | None:
    """
    Tipos de rateio que as `areas` enxergam. `None` significa TODOS (admin,
    quando "*" está entre as áreas). `area_map` vem do banco.
    """
    if "*" in (areas or []):
        return None
    tipos: set[str] = set()
    for area in areas or []:
        tipos.update(area_map.get(area, []))
    return tipos


def pode_ver(areas: list[str], tipo: str, area_map: dict[str, list[str]]) -> bool:
    """True se o usuário (por suas áreas) pode acessar o rateio `tipo`."""
    permitido = tipos_permitidos(areas, area_map)
    return permitido is None or tipo in permitido


def area_de_tipo(tipo: str, area_map: dict[str, list[str]]) -> str | None:
    """Área a que um rateio pertence (primeira correspondência no mapa)."""
    for area, tipos in area_map.items():
        if tipo in tipos:
            return area
    return None


def nivel_no_tipo(
    areas: list[str],
    niveis: dict[str, str],
    tipo: str,
    area_map: dict[str, list[str]],
) -> str | None:
    """
    Nível do usuário para o rateio `tipo`: "admin" (global), "admin_area" ou
    "operador". `None` se o usuário não tem acesso ao tipo.
    """
    if "*" in (areas or []):
        return "admin"
    area = area_de_tipo(tipo, area_map)
    if area is None or area not in (areas or []):
        return None
    return (niveis or {}).get(area, "operador")


def pode_auditar(
    areas: list[str],
    niveis: dict[str, str],
    tipo: str,
    area_map: dict[str, list[str]],
) -> bool:
    """
    True se o usuário pode ver dados de AUDITORIA do rateio `tipo` (salário/teto)
    e editar o cadastro da área dona do tipo — ou seja, admin_area ou admin global.
    """
    return nivel_no_tipo(areas, niveis, tipo, area_map) in ("admin", "admin_area")


def eh_admin_area_qualquer(areas: list[str], niveis: dict[str, str]) -> bool:
    """
    True se o usuário é admin global OU admin_area de QUALQUER área. Usado por
    cadastros de infraestrutura compartilhada entre rateios (ex.: centros de
    custo), que não pertencem a um único tipo.
    """
    if "*" in (areas or []):
        return True
    return any(n == "admin_area" for n in (niveis or {}).values())
