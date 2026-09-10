"""
Rateio de pagamento do plano de saúde da UNIMED.

Rateio fino: toda a lógica vem de `app.modules._plano_saude`
(`PagamentoPlanoSaudeBase`). Aqui só definimos a identidade e a operadora.
"""

from app.modules._plano_saude.base_module import PagamentoPlanoSaudeBase


class PagamentoUnimedRateio(PagamentoPlanoSaudeBase):
    """Pagamento UNIMED — casa colaboradores por CPF; reconcilia contra a NF."""

    tipo: str = "pagamento-unimed"
    nome: str = "Mensalidade Unimed"
    descricao: str = (
        "Pagamento da mensalidade Unimed à operadora, rateada por centro de custo "
        "e conciliada com a NF e o boleto."
    )
    operadora: str = "unimed"
