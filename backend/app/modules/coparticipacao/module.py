"""
Módulo de rateio: Coparticipação do Plano de Saúde — orquestração.

Amarra parser (lê o Consolidado) e calculator (faixa × tipo → valor, teto).
Recebe `dados_externos` com `colaboradores` (API, com salário) e `consenso`
(faixas/valores/teto, carregados do Postgres pelo router). Módulo puro.

Não há reconciliação (sem NF/boleto). A saída é o total a descontar por
colaborador; para o contrato base (`list[ItemRateio]`/CSV), cada colaborador
vira um item com o valor descontado e os detalhes em `extras`.
"""

from typing import Any

from app.modules.base import ItemRateio, RateioModule, ValidationResult

from . import calculator, export_erp, export_txt, parser
from .calculator import ItemCoparticipacao, ResultadoCoparticipacao


class CoparticipacaoRateio(RateioModule):
    """Rateio da coparticipação: desconto em folha por uso do plano."""

    tipo: str = "coparticipacao-plano-saude"
    nome: str = "Desconto de coparticipação"
    # A descrição aparece no cartão do painel com `line-clamp-2`: o que passa de
    # duas linhas (~110 caracteres) fica invisível. Por isso ela diz o que o
    # processo faz e qual é o documento, e nada mais — teto, rotina do ERP e
    # regras de conciliação vivem nas orientações da tela de importação.
    descricao: str = (
        "Desconto em folha da coparticipação do colaborador no plano de saúde, "
        "por faixa salarial e tipo de evento."
    )
    # Lança no ERP pela rotina de coparticipação (GPE): inclui o desconto por
    # matrícula, sem contrato e sem título. NÃO notifica o fiscal (não há NF).
    lanca_no_erp: bool = True

    def validar_inputs(
        self,
        arquivos: dict[str, bytes],
        dados_externos: dict[str, Any],
    ) -> ValidationResult:
        erros, alertas = parser.validar_estrutura(arquivos)
        if not (dados_externos or {}).get(calculator.CHAVE_COLABORADORES):
            alertas.append(
                "Lista de colaboradores da API ausente — sem salário não há faixa; "
                "todos cairão em divergência."
            )
        if not (dados_externos or {}).get(calculator.CHAVE_CONSENSO, {}).get("faixas"):
            erros.append(
                "Tabela de consenso (faixas/valores) não carregada — cadastro ausente."
            )
        return ValidationResult(valido=not erros, erros=erros, alertas=alertas)

    def processar_completo(
        self,
        arquivos: dict[str, bytes],
        dados_externos: dict[str, Any],
    ) -> ResultadoCoparticipacao:
        consolidados = parser.ler(arquivos, dados_externos)
        return calculator.calcular(consolidados, dados_externos)

    def processar(
        self,
        arquivos: dict[str, bytes],
        dados_externos: dict[str, Any],
    ) -> list[ItemRateio]:
        return self.resultado_para_itens(self.processar_completo(arquivos, dados_externos))

    def resultado_para_itens(self, resultado: ResultadoCoparticipacao) -> list[ItemRateio]:
        return [self._para_item_rateio(item) for item in resultado.itens]

    def gerar_txt_erp(
        self,
        itens: list[ItemRateio],
        competencia: str,
        empresa: str | None = None,
    ) -> str:
        """TXT de redundância p/ importação manual no ERP (fallback ao envio API).

        `competencia` no formato AAAAMM. Se `empresa` for informada, gera só os
        colaboradores dela. Layout posicional em [export_txt.py].
        """
        return export_txt.gerar(itens, competencia, empresa)

    def gerar_payload_erp(
        self,
        itens: list[dict[str, Any]],
        competencia: str,
        data_ocorrencia: str,
        empresa: str | None = None,
        matriculas: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Payload do POST de desconto em folha (rotina GPE) — ver [export_erp.py].

        `itens` são os do snapshot da execução (dicts), `competencia` a de
        PAGAMENTO (AAAAMM) e `data_ocorrencia` a data do registro (AAAAMMDD).
        `matriculas` restringe o lote (reenvio somente das recusadas).
        Mesmo conteúdo do TXT, outro transporte.
        """
        return export_erp.gerar(itens, competencia, data_ocorrencia, empresa, matriculas)

    def elegivel_erp(self, item: dict[str, Any]) -> bool:
        """True se o item (do snapshot) entra no lançamento em folha.

        Mesmo critério do payload — quem chama para decidir status/contagem usa
        esta função em vez de reimplementar a regra (PJ e teto ficam de fora).
        """
        return export_erp.elegivel(item)

    def resumo(self, resultado: ResultadoCoparticipacao) -> dict[str, Any]:
        """Resumo JSON-able do resultado (Decimais serializados pelo router)."""
        return {
            "itens": [vars(i) for i in resultado.itens],
            "divergencias": [vars(d) for d in resultado.divergencias],
            "avisos": resultado.avisos,
            "total_descontado": resultado.total_descontado,
        }

    @staticmethod
    def _para_item_rateio(item: ItemCoparticipacao) -> ItemRateio:
        historico = (
            f"Coparticipação {item.faixa} — {item.num_eventos} evento(s)"
            + (" (teto aplicado)" if item.teto_aplicado else "")
        )
        return ItemRateio(
            colaborador_cpf=item.cpf,
            colaborador_nome=item.nome,
            departamento="",
            centro_de_custo="",  # coparticipação é desconto em folha, não CC
            valor=item.valor_descontado,
            historico=historico,
            extras={
                "matricula": item.matricula,
                "filial": item.filial,
                "operadora": item.operadora,
                "empresa": item.empresa,
                "salario": str(item.salario),
                "faixa": item.faixa,
                "num_eventos": str(item.num_eventos),
                "valor_bruto": str(item.valor_bruto),
                "teto": str(item.teto),
                "teto_aplicado": "sim" if item.teto_aplicado else "nao",
                "pj": "sim" if item.pj else "nao",
                # Fora do lançamento automático (PJ ou teto) — os exports leem daqui.
                "bloqueado_envio": "sim" if item.bloqueado_envio else "nao",
                "motivo_bloqueio": item.motivo_bloqueio,
            },
        )
