"""
Fonte ÚNICA (banco) dos dados fiscais de empresas/fornecedores.

Substitui os mapas que viviam em `config.py` (protheus_rests,
protheus_rotina_por_empresa, protheus_fornecedor_cnpj, prenota_*) e em
`_plano_saude/validators.py` (_EMPRESAS_POR_NOME/_CNPJ, _CNPJ_*). Expõe as
MESMAS estruturas/semântica dos antigos helpers, para uma troca localizada e de
comportamento idêntico (mesma resolução, só muda a origem: código → banco).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organizacao_fiscal import Empresa, Fornecedor


@dataclass
class ConfigFiscal:
    """Snapshot dos mapas de empresa/fornecedor carregado do banco."""

    empresa_por_rest: dict[str, str]          # rest -> nome  (== antigo protheus_rests)
    rest_por_empresa: dict[str, str]          # NOME_UPPER -> rest
    rotina_map: dict[str, str]                # nome_lower -> "ae" | "pre_nota"
    prenota_map: dict[str, tuple[str, str]]   # nome_lower -> (produto, filial)
    fornecedor_map: dict[str, str]            # fornecedor_lower -> CNPJ (dígitos)
    empresas_por_nome: dict[str, str]         # KEYWORD -> nome (detecção em PDF)
    empresas_por_cnpj: dict[str, str]         # cnpj_formatado -> nome
    cnpj_operadora: dict[str, str]            # operadora_lower -> cnpj_formatado

    # Helpers com a MESMA semântica dos antigos `Settings.*`.
    def rest_da_empresa(self, empresa: str) -> str | None:
        return self.rest_por_empresa.get((empresa or "").strip().upper())

    def rotina_erp(self, empresa: str) -> str:
        return self.rotina_map.get((empresa or "").strip().lower(), "ae")

    def prenota(self, empresa: str) -> tuple[str, str]:
        return self.prenota_map.get((empresa or "").strip().lower(), ("", ""))

    def fornecedor_cnpj(self, fornecedor: str) -> str:
        return self.fornecedor_map.get((fornecedor or "").strip().lower(), "")

    def rests_do_tipo(self, tipo: str, rests_por_tipo: dict[str, list[str]]) -> dict[str, str]:
        """Rests (rest -> empresa) a consultar p/ um rateio. Sem mapa -> todos."""
        permitidos = rests_por_tipo.get(tipo)
        if not permitidos:
            return dict(self.empresa_por_rest)
        return {r: e for r, e in self.empresa_por_rest.items() if r in permitidos}


def carregar_config_fiscal(db: Session) -> ConfigFiscal:
    empresas = db.scalars(select(Empresa)).all()
    fornecedores = db.scalars(select(Fornecedor)).all()
    return ConfigFiscal(
        empresa_por_rest={e.rest: e.nome for e in empresas if e.rest},
        rest_por_empresa={e.nome.strip().upper(): e.rest for e in empresas if e.rest},
        rotina_map={e.nome.strip().lower(): e.rotina_erp for e in empresas},
        prenota_map={
            e.nome.strip().lower(): (e.prenota_produto, e.prenota_filial) for e in empresas
        },
        # CNPJ do fornecedor para o ERP = os dígitos do CNPJ cadastrado (mesmo
        # dado, só dígitos). O CNPJ (formatado) é único no cadastro.
        fornecedor_map={f.nome.strip().lower(): re.sub(r"\D", "", f.cnpj) for f in fornecedores},
        empresas_por_nome={e.nome.strip().upper(): e.nome for e in empresas},
        empresas_por_cnpj={e.cnpj: e.nome for e in empresas if e.cnpj},
        cnpj_operadora={f.nome.strip().lower(): f.cnpj for f in fornecedores if f.cnpj},
    )
