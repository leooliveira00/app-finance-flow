"""
Biblioteca COMPARTILHADA dos rateios de pagamento de plano de saúde.

Reúne a lógica comum às operadoras — leitura das planilhas (`parser`), cálculo
do rateio (`calculator`), reconciliação com NF/boleto (`validators`) e a
orquestração base (`base_module.PagamentoPlanoSaudeBase`).

Este pacote começa com `_`, então NÃO é descoberto como rateio pelo registry.
Os rateios concretos, um por operadora, ficam em pacotes próprios que herdam da
base e definem `tipo`/`descricao`/`operadora`:
- `app/modules/pagamento_unimed/`   (casa por CPF; reconcilia contra NF)
- `app/modules/pagamento_bradesco/` (casa por nome; reconcilia contra boleto)

A empresa, o centro de custo e a classe de valor vêm da API de colaboradores
(fonte da verdade), injetados como `dados_externos` pelo router — a lógica
permanece pura (sem banco nem rede).
"""
