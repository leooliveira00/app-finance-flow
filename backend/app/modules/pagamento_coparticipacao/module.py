"""
Rateio do PAGAMENTO da coparticipação do plano de saúde — UNIMED.

Processo análogo à mensalidade (`pagamento_unimed`): rateia por centro de custo
cruzando com a API, reconcilia contra NF/boleto por empresa e lança pré-nota/AE
no ERP. A diferença é só o FORMATO DE ENTRADA — aqui um consolidado por
beneficiário (`VLR_PARTICIPACAO`) em vez da planilha mensal.

Por isso este módulo herda toda a orquestração de `PagamentoPlanoSaudeBase`
(cálculo/reconciliação/CSV/resumo/lançamento no ERP) e apenas TROCA O PARSER,
usando `parser_copart` no lugar de `_plano_saude.parser`. Nada da mensalidade é
alterado.
"""

from typing import Any

from app.modules._plano_saude import calculator, validators
from app.modules._plano_saude.base_module import PagamentoPlanoSaudeBase
from app.modules._plano_saude.calculator import ResultadoRateio
from app.modules.base import ValidationResult

from . import parser_copart


class PagamentoCoparticipacaoUnimedRateio(PagamentoPlanoSaudeBase):
    """Pagamento da coparticipação UNIMED — consolidado por beneficiário."""

    tipo: str = "pagamento-coparticipacao-unimed"
    nome: str = "Fatura de coparticipação Unimed"
    descricao: str = (
        "Pagamento da fatura de coparticipação à Unimed, rateada por centro de custo "
        "e conciliada com a NF e o boleto."
    )
    operadora: str = "unimed"

    def validar_inputs(
        self,
        arquivos: dict[str, bytes],
        dados_externos: dict[str, Any],
    ) -> ValidationResult:
        """Exige o consolidado; alerta (não bloqueia) NF/boleto e colaboradores."""
        erros, alertas = parser_copart.validar_estrutura(arquivos)

        documentos = validators.classificar_documentos(arquivos)
        if not any(v and v[0] == self.operadora for v in documentos.values()):
            alertas.append(
                f"Nenhuma NF/boleto da {self.operadora.upper()} enviada — a "
                "reconciliação dos valores faturados não será possível."
            )
        if not (dados_externos or {}).get(calculator.CHAVE_COLABORADORES):
            alertas.append(
                "Lista de colaboradores da API ausente — todos os titulares "
                "cairão em divergência."
            )
        return ValidationResult(valido=not erros, erros=erros, alertas=alertas)

    def processar_completo(
        self,
        arquivos: dict[str, bytes],
        dados_externos: dict[str, Any],
    ) -> ResultadoRateio:
        """Rateio + reconciliação da coparticipação (só a operadora deste rateio)."""
        planilhas = [
            p
            for p in parser_copart.ler(arquivos, dados_externos)
            if p.operadora == self.operadora
        ]
        resultado = calculator.calcular(planilhas, dados_externos)

        documentos = [
            d
            for d in validators.extrair_documentos(arquivos)
            if d.operadora == self.operadora
        ]
        resultado.reconciliacao = validators.reconciliar(resultado, documentos)
        return resultado
