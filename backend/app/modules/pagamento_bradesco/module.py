"""
Rateio de pagamento do plano de saúde do Bradesco Saúde.

Rateio fino: toda a lógica vem de `app.modules._plano_saude`
(`PagamentoPlanoSaudeBase`). Aqui só definimos a identidade e a operadora.
"""

from app.modules._plano_saude.base_module import PagamentoPlanoSaudeBase


class PagamentoBradescoRateio(PagamentoPlanoSaudeBase):
    """
    Pagamento Bradesco — casa colaboradores por NOME do titular (a planilha não
    traz CPF) e reconcilia contra o boleto. O casamento por nome sinaliza
    homônimos como divergência.
    """

    tipo: str = "pagamento-bradesco"
    nome: str = "Mensalidade Bradesco"
    descricao: str = (
        "Pagamento da mensalidade Bradesco à operadora, rateada por centro de custo "
        "e conciliada com o boleto."
    )
    operadora: str = "bradesco"
