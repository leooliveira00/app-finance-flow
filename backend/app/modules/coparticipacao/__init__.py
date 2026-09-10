"""
Módulo de rateio: Coparticipação do Plano de Saúde.

Objetivo: calcular o valor a DESCONTAR EM FOLHA de cada colaborador pelo uso
(coparticipação) do plano, a partir do Consolidado enviado pelas operadoras
(Unimed e Bradesco seguem o mesmo formato).

Regra: cada evento (linha do Consolidado) vale um valor FIXO da tabela de
consenso, indexada por (faixa salarial × tipo de exame). A faixa vem do salário
do colaborador (API); o tipo vem da coluna `Procedimento`. Soma-se por
colaborador (titular + dependentes, agrupados por `CPF Titular`) e aplica-se um
TETO de X% do salário (parametrizável; alerta ao estourar).

Não há documento de reconciliação — a saída é o total a descontar por colaborador.

A tabela de consenso (faixas + valores + teto) é cadastro parametrizável
(Postgres); o router a carrega e injeta em `dados_externos`, junto dos salários
da API — o módulo permanece puro.
"""
