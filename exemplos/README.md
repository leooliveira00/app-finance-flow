# Exemplos

Documentos fictícios para demonstrar o processamento do FinanceFlow sem
depender de dados reais nem de um ERP configurado.

## `consolidado_coparticipacao_unimed.xlsx`

Planilha no formato "Consolidado de coparticipação" (layout Unimed, com as
colunas `Nome Empresa`, `CPF Titular`, `Nome Titular`, `Nome Beneficiário`,
`Data Atendimento`, `Procedimento`, `Valor Coparticipação`). Faça upload dela
na tela do processo **Desconto de coparticipação** (login com qualquer usuário
de demonstração; ver README da raiz).

Os CPFs foram escolhidos para casar com o cadastro fictício de colaboradores
(`ColaboradorDemo`, semeado automaticamente pelo backend; ver
`backend/app/db/seed.py`), que substitui a consulta ao Protheus enquanto
`PROTHEUS_READ_BASE_URL` não estiver configurada. Cada colaborador da planilha
exercita um cenário diferente das regras de negócio:

| Colaborador | CPF | Cenário |
|---|---|---|
| Ana Beatriz Souza | 111.222.333-96 | Titular e 1 dependente: item normal, 2 eventos (consulta e exame simples) |
| Carlos Eduardo Lima | 222.333.444-05 | 1 evento classificado (consulta) e 1 procedimento não reconhecido ("Exame Laboratorial"): item normal com uma divergência ao lado |
| Fernanda Ribeiro Alves | 333.444.555-08 | Salário baixo (R$ 1.300) e família grande: 27 consultas no mês estouram o teto de 20% do salário (R$ 260) e a colaboradora fica **bloqueada** para tratativa manual |
| Roberto Nunes Costa | 444.555.666-19 | Cadastrado como **DEMITIDO**, o que gera a divergência "colaborador desligado" |
| Marcos Vinícius Teixeira | 555.666.777-20 | CPF que só existe na planilha, não no cadastro, o que gera a divergência "titular não encontrado" (propositalmente ausente do seed) |
| Juliana Martins Pereira | 666.777.888-30 | Salário alto (faixa 6), 2 tipos de evento (consulta e especial): item normal |

Resultado esperado ao processar: **4 itens**, **3 divergências** e **1 aviso**
(teto atingido), cobrindo o caminho de sucesso e as principais divergências
do módulo numa única execução.

Nenhum CPF, nome ou valor aqui corresponde a uma pessoa real.
