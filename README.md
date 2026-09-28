# FinanceFlow

Aplicação web full stack para **automação de processos financeiros**: lançamento
e processamento de contas, rateio de valores por centro de custo e integração
com um ERP. Nasceu como um protótipo de UI e evoluiu para uma aplicação real,
com backend, banco de dados, autenticação e uma camada de integração com ERP,
construída para demonstrar um fluxo de automação financeira de ponta a ponta,
do upload do documento ao lançamento contábil.

## Problema

Processos de rateio contábil, que consistem em dividir uma fatura entre várias
empresas ou centros de custo, conferir o valor rateado contra a nota ou boleto
original e lançar o resultado no ERP, costumam ser feitos manualmente em
planilha, um trabalho repetitivo e sujeito a erro humano (percentuais errados,
esquecimento de um centro de custo, lançamento em duplicidade). O FinanceFlow
automatiza esse fluxo: upload do documento → cálculo do rateio → conferência
automática contra o valor faturado → lançamento no ERP → notificação de quem
precisa saber.

## Principais funcionalidades

- **Processamento de rateio**: upload de planilhas/PDFs, cálculo por centro de
  custo, com múltiplos módulos de rateio plugáveis (mensalidade de plano de
  saúde, desconto de coparticipação em folha, faturas de telefonia).
- **Reconciliação automática**: o valor calculado é comparado com o total do
  documento fiscal (NF/boleto), gerando alertas quando não batem, sem travar
  o processo, para o usuário decidir.
- **Integração com ERP**: duas rotinas de lançamento (título por empresa via
  Autorização de Entrega/pré-nota; lançamento em lote por matrícula na folha de
  pagamento), com trava contra envio parcial e reenvio seletivo apenas do que
  falhou.
- **Histórico e auditoria**: toda execução fica registrada, incluindo quem
  processou, o resultado, o que foi enviado ao ERP e quem foi notificado por
  e-mail.
- **Autenticação e permissões**: login com JWT e segregação por área. Cada
  usuário só vê os processos da(s) área(s) a que pertence; administradores
  gerenciam cadastros (empresas, fornecedores, centros de custo, usuários).
- **Notificação por e-mail**: ao concluir um lançamento, o time responsável é
  notificado com os documentos e os números dos títulos gerados.

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | React 19 + Vite + Tailwind CSS v4, TypeScript |
| Backend | Python + FastAPI, SQLAlchemy 2.0 |
| Banco de dados | PostgreSQL |
| Autenticação | JWT (bcrypt para senhas) |
| Infraestrutura | Docker Compose (nginx no frontend, uvicorn no backend) |
| Qualidade | ruff + mypy (backend), tsc --noEmit (frontend) |

## Arquitetura

```
frontend/    SPA React, máquina de estados (sem router), chamadas centralizadas em src/api.ts
backend/     FastAPI, em camadas: routers/ (HTTP) → services/ (integrações) →
             modules/ (regra de negócio de cada rateio, plugável) → models/ + db/ (ORM)
docker-compose.yml   nginx (frontend, proxy /api/) + uvicorn (backend) + postgres
```

Cada tipo de rateio é um módulo independente (`backend/app/modules/`) descoberto
automaticamente no startup. Adicionar um novo processo de rateio não exige
alterar o restante do backend, só implementar o módulo (ver `_template/`).

A integração com o ERP é isolada em `services/protheus.py` e `services/erp.py`,
com dois eixos configuráveis por variável de ambiente: uma base de **leitura**
(consulta de colaboradores) e uma de **escrita** (lançamentos), permitindo
apontar cada uma para ambientes diferentes. Por exemplo, é possível consultar
dados reais e escrever apenas num ambiente de teste do ERP até a validação de
um go-live.

**Limitação conhecida: um processo de backend.** O último resultado processado
(antes de ser confirmado como execução) fica num dicionário em memória,
por usuário e tipo de rateio (`_ULTIMO_RESULTADO` em
`backend/app/routers/rateio.py`), e serve os downloads de CSV/TXT dessa etapa.
Isso é correto com um único worker do uvicorn e uma única réplica, que é como o
compose sobe o serviço (a réplica única já é exigida porque as migrações rodam
na subida). Com mais de um worker, o download poderia cair num processo que não
processou o arquivo e responder 404; um restart do container também descarta
esse resultado, e basta processar de novo. Execuções confirmadas não dependem
disso: ficam no Postgres e seus arquivos são gerados a partir do banco. Escalar
horizontalmente exigiria mover esse estado para um store compartilhado (Redis ou
tabela com TTL).

Mais detalhes de arquitetura e das regras de negócio de cada módulo estão em
[CLAUDE.md](CLAUDE.md).

## Execução local

Pré-requisitos: Docker e Docker Compose.

```bash
cp .env.example .env                 # infraestrutura do compose (senha do banco obrigatória)
cp backend/.env.example backend/.env # integrações (ERP, SMTP, JWT)
docker compose up -d
```

Preencha pelo menos `POSTGRES_PASSWORD` (raiz) e `JWT_SECRET` (backend, 32+
caracteres, gerado com `openssl rand -hex 48`). Acesse em **http://localhost:8080**
(ajustável via `FRONTEND_PORT` no `.env`, se a porta já estiver em uso).

Este repositório já inclui um `docker-compose.override.yml` que remove a
dependência de um proxy reverso externo (Traefik) e é aplicado automaticamente
pelo Docker Compose. Alterações em código Python exigem rebuild
(`docker compose up -d --build backend`); não há hot reload por padrão.

### Verificações automatizadas

Não há suíte de testes. O que existe precisa passar antes de qualquer entrega:

```bash
docker compose exec backend ruff check app   # lint
docker compose exec backend mypy app         # tipos
cd frontend && npm run lint                  # tsc --noEmit
```

## Dados de demonstração

O banco sobe vazio e é populado por um seed idempotente na primeira subida:
usuários, empresas e fornecedores fictícios, faixas de coparticipação e
centros de custo de exemplo. Nada aqui corresponde a dados reais de nenhuma
organização.

Usuários de demonstração (login por e-mail):

| E-mail | Senha | Perfil |
|---|---|---|
| `admin@financeflow.local` | `admin` | Administrador (todas as áreas) |
| `rh@financeflow.local` | `rh` | Administrador da área RH |
| `operador@financeflow.local` | `operador` | Operador da área RH |

## Exemplo de uso

[`exemplos/consolidado_coparticipacao_unimed.xlsx`](exemplos/consolidado_coparticipacao_unimed.xlsx)
é uma planilha fictícia pronta para subir na tela do processo **Desconto de
coparticipação**. Ela foi montada para exercitar as principais regras de
negócio numa única execução. Com os usuários de demonstração acima, o
resultado esperado é o seguinte:

| Colaborador | Resultado |
|---|---|
| Ana Beatriz Souza | Item normal: titular e 1 dependente |
| Carlos Eduardo Lima | Item normal + 1 divergência (procedimento não reconhecido) |
| Fernanda Ribeiro Alves | Bloqueado: estourou o teto de 20% do salário (família com muitos eventos no mês) |
| Roberto Nunes Costa | Divergência: colaborador desligado |
| Marcos Vinícius Teixeira | Divergência: titular não encontrado no cadastro |
| Juliana Martins Pereira | Item normal: salário alto, dois tipos de evento |

Ver [`exemplos/README.md`](exemplos/README.md) para o detalhe de cada cenário.

## Integração com ERP

O backend implementa a integração completa com um ERP no padrão Protheus
(autenticação, paginação de consulta, montagem do payload de lançamento,
reconciliação de valores e tratamento de envio parcial) como camada de
serviço isolada (`services/protheus.py`, `services/erp.py`), configurável só
por variável de ambiente (URLs, credenciais, timeouts).

Como essa integração originalmente dependia de um ambiente de ERP privado,
`PROTHEUS_READ_BASE_URL` vem **vazia** no `.env.example`: sem ela, o
processamento usa um pequeno cadastro fictício de colaboradores
(`ColaboradorDemo`, populado pelo seed, responsável por fazer o exemplo acima
funcionar) em vez de consultar um Protheus real. Login e os demais fluxos da
aplicação funcionam normalmente; só o passo de "lançar no ERP" (que usa a
base de **escrita**, `PROTHEUS_WRITE_BASE_URL`) exige apontar as variáveis
para uma instância real (ou de teste) de um Protheus. O fallback existe
somente para a etapa de leitura e cálculo, nunca para o lançamento. A
arquitetura e as regras de negócio da integração (payload, retry,
reconciliação) estão documentadas em detalhe no [CLAUDE.md](CLAUDE.md).

## Histórico e versionamento

Esta é uma versão pública e anonimizada de uma aplicação desenvolvida para uso
interno. O histórico original foi **consolidado num único commit inicial** para
a publicação, pois os commits originais continham informações privadas. Os commits posteriores a ele seguem o fluxo normal do projeto.

O projeto segue [Conventional Commits](https://www.conventionalcommits.org/) e é
versionado como uma unidade (backend e frontend juntos) via
[semantic-release](https://semantic-release.gitbook.io/): a versão, o
[CHANGELOG.md](CHANGELOG.md) e a tag são gerados a partir das mensagens de
commit (`npm run release`, na raiz). A versão em execução aparece no rodapé da
interface e em `GET /api/health`. O fluxo completo está descrito na seção
"Versionamento" do [CLAUDE.md](CLAUDE.md).
