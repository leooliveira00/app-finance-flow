# CLAUDE.md

Guia para o Claude Code (claude.ai/code) ao trabalhar neste repositório.

## O que é este projeto

**FinanceFlow**: plataforma modular para lançamentos de **rateio contábil**
integrada ao ERP **Protheus**. Nasceu como um protótipo de UI (Google AI Studio)
mas **evoluiu para uma aplicação full-stack real**: frontend React + backend
FastAPI + Postgres, com autenticação, integrações com o Protheus e envio de
e-mail. **Ignore descrições antigas de "protótipo mock sem backend"**: hoje há
backend, banco e integrações reais (ainda que algumas em ambiente de teste).

O domínio: RH sobe as planilhas das operadoras de plano de saúde (Unimed,
Bradesco) e/ou eventos de coparticipação; a plataforma processa, rateia por
centro de custo, reconcilia contra NF/boleto, e lança no Protheus (Autorização
de Entrega ou pré-nota), notificando o dep. fiscal por e-mail.

## Estrutura do repositório

```
backend/     API FastAPI + Postgres (código Python)
frontend/    SPA React 19 + Vite + Tailwind v4 (servido por nginx em prod)
docker-compose.yml   sobe frontend (nginx/Traefik) + backend (uvicorn) + postgres
dados/       arquivos de dados/exemplo (não versionados como fonte de verdade)
scripts/     utilitários de operação (dump de cadastros, versão do backend)
package.json + .releaserc.json   ferramental de release (semantic-release)
```

O acesso em produção é por mesma origem: nginx serve o frontend e faz proxy de
`/api/` para o backend. O frontend é publicado via Traefik em `financeflow.example.com`.

## Comandos

### Backend (`backend/`)
```bash
# Via docker-compose (recomendado; sobe API + Postgres juntos):
docker compose up -d backend postgres  # API em 127.0.0.1:8000, docs em /docs
# GATE do backend (rode após alterações; é a única verificação automatizada):
docker compose exec backend ruff check app
docker compose exec backend mypy app
```
O gate é `ruff` + `mypy`, configurados em [pyproject.toml](backend/pyproject.toml).
Não há suíte de testes (existe um `backend/tests/` com um arquivo, mas `pytest`
não está nas dependências). Na subida, o `lifespan`
([main.py](backend/app/main.py)) cria o schema (`create_all`), aplica migrações
idempotentes ([migracoes.py](backend/app/db/migracoes.py)), roda o seed inicial e
dispara a descoberta de módulos de rateio. Como a migração roda no `lifespan`, o
serviço precisa ficar em **réplica única**. O mesmo vale para os workers: o
último resultado processado (pré-confirmação) vive em memória
(`_ULTIMO_RESULTADO` em [rateio.py](backend/app/routers/rateio.py)) e serve os
downloads CSV/TXT dessa etapa, então **não adicione `--workers`** ao uvicorn
sem antes mover esse estado para um store compartilhado (Redis ou tabela com
TTL). Execuções confirmadas já estão no Postgres e não são afetadas.

**Hot reload não é da imagem.** A imagem sobe o uvicorn sem `--reload`, como
usuário `app` (não-root), com `tini` como PID 1 e `--proxy-headers`. Mudança em
código exige rebuild (`docker compose up -d --build backend`); mudança em
`.env` exige recriar (`docker compose up -d backend`), não `restart`.

**Rodar sem o Traefik** (qualquer host que não o tenha publicado, ex.: Docker
Desktop local): `docker-compose.override.yml` é **versionado** de propósito
e o Compose o carrega automaticamente: tira o frontend da rede
`traefik-public`, zera as labels de roteamento e publica o frontend em
`http://localhost:${FRONTEND_PORT:-8080}`. **Hosts que JÁ têm Traefik
(dev/produção) devem apagar ou renomear esse arquivo** antes de subir; do
contrário o app sobe sem TLS e sem o roteamento por domínio (ver "Dois hosts"
abaixo).

### Frontend (`frontend/`)
```bash
npm install
npm run dev        # dev server em 0.0.0.0:3000 (proxy /api -> backend)
npm run build      # build de produção (vite)
npm run preview    # serve o dist/
npm run lint       # SÓ checagem de tipos: `tsc --noEmit` (não há ESLint nem testes)
```
Rode `npm run lint` após alterações no frontend: é a única verificação
automatizada disponível.

## Arquitetura do backend

FastAPI com **application factory** (`create_app`) e routers sob o prefixo `/api`.
Camadas: `routers/` (HTTP) → `services/` (integrações/regras de infra) →
`modules/` (regras de negócio puras de cada rateio) → `models/` + `db/` (ORM
SQLAlchemy 2.0 / Postgres).

- **Módulos de rateio** (`app/modules/`): cada rateio é um pacote que herda de
  `RateioModule` ([base.py](backend/app/modules/base.py)) e é **descoberto
  automaticamente** no startup ([registry.py](backend/app/modules/registry.py)).
  **Para adicionar um rateio, copie `_template/` para um novo pacote e
  implemente**; nada mais precisa mudar. Pacotes com prefixo `_` (ex.:
  `_template`, `_plano_saude`) são moldes/bases compartilhadas, não rateios
  ativos. Ativos hoje: `coparticipacao` (desconto em folha, rotina GPE),
  `pagamento_unimed`/`pagamento_bradesco` (mensalidade, AE/pré-nota),
  `pagamento_coparticipacao` (fatura de coparticipação Unimed, mesma rotina de
  AE/pré-nota) e `pagamento_claro` (telefonia, um título por boleto; ver
  "Um título por DOCUMENTO" abaixo).
- **Services** (`app/services/`): `protheus.py` (colaboradores + inclusões),
  `erp.py`, `email.py`/`notificacao.py` (SMTP p/ dep. fiscal),
  `organizacao.py` (auth + CRUD usuários/áreas), `cadastro.py`.
- **Duas rotinas de lançamento no ERP**: `lanca_no_erp` não implica título:
  - *Pagamento* (AE/pré-nota): um título por empresa, sobre contrato de parceria,
    com trava anti-parcial e reconciliação da NF (`erp.enviar_rateio`).
  - *Desconto em folha* (coparticipação, rotina GPE): POST em LOTE por empresa,
    uma entrada por **matrícula × operadora** (o `RHO_CODFOR`, 03 Bradesco / 07
    Unimed, é o que identifica o plano; dois planos = duas entradas), sem
    contrato/NF/título
    ([erp.enviar_coparticipacao](backend/app/services/erp.py); payload em
    [export_erp.py](backend/app/modules/coparticipacao/export_erp.py)). Exige a
    **competência de pagamento** (a folha do desconto, informada no envio,
    distinta da competência dos eventos) e o ERP pode responder 200 com falha
    PARCIAL (`totalOk` < enviados), que NÃO é tratado como sucesso.

    **Envio parcial e reenvio seletivo**: no 200 parcial o ERP identifica o registro
    recusado pela POSIÇÃO no lote, contando de 1 (`errors.erros: [{"item_26": …}]`),
    e enterra o motivo em `detailedMessage` ("Mensagem do erro: [...]"). O serviço
    traduz posição → matrícula/nome, grava `enviados`/`aceitos`/`matriculas_pendentes`
    em `EnvioErp` e a resposta bruta em `EnvioTentativa.resposta_erp`. Status
    `parcial` (empresa e execução): nem erro, nem enviado. O **reenvio manda só as
    matrículas recusadas**; as aceitas não voltam (seriam desconto em dobro).
    Empresa parcial SEM lista identificada não é reenviada automaticamente: sem
    saber quais falharam, reenviar tudo duplicaria quem já entrou. O TXT posicional
    segue como fallback de importação manual.

    **Quem NÃO vai ao lançamento automático** (regra de negócio; `bloqueado_envio`
    no item, com `motivo_bloqueio` exibido na UI): colaborador que **atinge o teto
    do percentual** (exige tratativa manual) e **PJ**, cujo desconto é cobrado na
    nota (tem CSV próprio em `GET /api/rateio/{tipo}/pj.csv`). O critério é único
    (`modulo.elegivel_erp`) e vale para o payload, o TXT e o fechamento do status:
    divergir faria o TXT importar justamente quem a API deixou de fora.
    O **teto é da PESSOA** (percentual do salário sobre a soma dos planos), não do
    plano. Quem tem os **dois planos** entra num lançamento ÚNICO por matrícula,
    com os valores SOMADOS e o código do fornecedor consolidado
    (`COD_FORNECEDOR_CONSOLIDADO`, hoje 07; a folha aceita um desconto por
    matrícula na competência); quem tem um plano mantém o código dele. A divisão
    por operadora permanece no resultado, na tela e no CSV, para auditoria.

    **Transferência no grupo**: o mesmo CPF aparece em mais de uma empresa
    (~38 casos hoje em Vertex+Zenith). A empresa do lançamento é sempre a do
    registro **não-demitido** que forneceu o salário: `empresa`/`matricula`/`filial`
    saem do mesmo registro escolhido em
    [resolver_duplicados](backend/app/services/protheus.py), senão o desconto
    entraria na folha de onde a pessoa já saiu. Quando os registros empatados
    apontam para **destinos diferentes** (empresa/matrícula divergentes, ex.: ativo
    nas duas com o mesmo salário), a escolha é indecidível: o colaborador é marcado
    e fica fora do lançamento automático, com aviso. Empatados que apontam para o
    MESMO destino (a API repete o registro) não são ambiguidade.

    **Salário zerado**: registro sem salário é cadastro funcional/casca (ex.:
    "Rh Vertex"), não vínculo com folha; na coparticipação vira divergência
    `sem_salario` e não gera item (sem salário não há faixa; passar geraria um
    desconto de R$ 0,00 parecendo válido). A regra fica no `calculator` da
    coparticipação, NÃO no cliente Protheus: os rateios de *pagamento* usam a mesma
    lista só para achar centro de custo/classe; lá o salário é irrelevante e
    descartar registros tiraria do rateio demitidos que a operadora ainda cobra.
  - *Um título por DOCUMENTO* (telefonia Claro): AE sobre contrato de parceria,
    como o pagamento, mas **um título por boleto**, todos numa única empresa
    (`protheus_claro_empresa`). O módulo declara o que compõe cada título
    (`titulos_erp`) e o serviço genérico `erp.enviar_titulos_por_referencia` faz
    contrato → casamento CC→item → POST. A unidade de envio é
    `(empresa, referencia)`: a referência é a conta da Claro, e sem ela o segundo
    boleto sobrescreveria o primeiro no `EnvioErp`. Trava ANTI-PARCIAL: valida
    todos os boletos antes de postar qualquer um (lançar 7 de 8 é parcial), e a
    notificação ao fiscal só sai quando todos entraram: um e-mail com todos os
    boletos e títulos. A quantidade de boletos é livre (1, 2 ou N).
  Em ambas, empresa com status `enviado` nunca é reenviada; na folha, essa trava
  é o que evita descontar duas vezes do colaborador.
- **Cadastro de fornecedores** (`Fornecedor`, tela Configurações › Cadastros ›
  Fornecedores): é o CNPJ que vai como fornecedor do título, resolvido pela chave
  que o módulo declara em `RateioModule.fornecedor` ("unimed", "bradesco",
  "claro"). Chamava-se `Operadora`, nome que só descrevia o plano de saúde. O
  cadastro manda; `settings.protheus_fornecedor_cnpj` é apenas o padrão de fábrica
  (`erp._cnpj_fornecedor`), então um fornecedor novo lança antes de ser cadastrado.
- **Config** ([config.py](backend/app/config.py)): `pydantic-settings` lê tudo do
  `.env` (ver `.env.example`): credenciais Protheus, SMTP, JWT, `DATABASE_URL`,
  CORS, mapas rest→empresa. Sempre acesse via `get_settings()` (cacheado).

### Autenticação e autorização (IMPLEMENTADO, não é mock)

- **Login**: `POST /api/auth/login` valida usuário/senha (bcrypt) contra o
  Postgres e emite **JWT** (HS256, 8h). `GET /api/auth/me` restaura a sessão.
  Token vai em `Authorization: Bearer` (frontend guarda no `localStorage`).
- **Segregação por área**: `Usuario` ↔ `Area` (M2M); `AreaRateio` mapeia
  `área → tipos de rateio` ([models/auth.py](backend/app/models/auth.py)). Um
  usuário só vê os rateios das suas áreas (`GET /api/modulos` filtra;
  [auth/service.py](backend/app/auth/service.py) resolve `tipos_permitidos`).
- **Níveis são BINÁRIOS**: `Usuario.admin` true/false (admin é representado pela
  área `"*"`). Admin vê tudo e gerencia cadastros; não-admin ("operador") é
  restrito às suas áreas e fica em **modo leitura** nas Configurações. **Não há**
  papel "operador" nomeado, terceiro nível, nem permissão por ação dentro de um
  rateio: quem acessa a área executa o fluxo inteiro (processar → confirmar →
  enviar ao ERP → notificar). Dependências: `usuario_atual` (autenticado) e
  `usuario_admin` (exige admin) em [auth/deps.py](backend/app/auth/deps.py).
- Seed de teste: `admin/admin` (vê tudo) e `rh/rh` (área RH); ver
  [auth/seed.py](backend/app/auth/seed.py).

## Arquitetura do frontend

SPA React 19 renderizada em `#root` via `src/main.tsx`. A aplicação é uma
**máquina de estados em `src/App.tsx`**, sem router nem estado global; navegação
e estado compartilhado vivem em `useState` e descem por props (incluindo
`addToast`). Se não houver `usuario`, renderiza `LoginScreen`.

Duas dimensões de navegação (em `src/types.ts`):
- `ActiveTab` (`dashboard | historico | configuracoes`): abas da sidebar.
- `ViewState` (`list | execution-flow | result-view | success-view`): sub-telas
  do fluxo de rateio dentro do dashboard.

`renderMainContent()` em `App.tsx` faz o switch. Fluxo: `DashboardScreen` →
`ExecutionFlowScreen` (upload + processamento reais via API) → `ResultScreen`/
`CoparticipacaoResultScreen` → `ConfirmationModal` → `SuccessView` (persiste a
execução no backend). `src/api.ts` centraliza **todas** as chamadas à API.

Configurações (`components/config/`): `UsuariosConfig`, `SetoresConfig` (áreas),
`CentroCustoConfig`, `EmpresasConfig`, `FornecedoresConfig`, `CoparticipacaoConfig`,
`PagamentoConfig`: escritas exigem admin (o backend rejeita não-admins; a UI
mostra modo leitura). Derivação de papel no front centralizada em
[permissoes.ts](frontend/src/permissoes.ts).

### Destinatários das notificações

`Para` = departamento fiscal, `Cópia` = cópia permanente + e-mails da **área**
dona do rateio, `Reply-To` = a área (a resposta do fiscal cai em quem tratou).
Regra única em [services/notificacao_config.py](backend/app/services/notificacao_config.py).
O fiscal e a cópia permanente ficam em `ConfigNotificacao` (Configurações ›
Organização › Notificações), inicializada a partir de `FISCAL_EMAILS` do `.env`
na primeira leitura; a cópia por área é `Area.emails_copia`, editada em Setores e
permissões: a área é dona dos processos, então um rateio novo herda os
responsáveis sem cadastro adicional. Formato de e-mail é validado no CADASTRO
(422), nunca no envio: descobrir endereço inválido ao notificar deixaria o rateio
já lançado no ERP e o fiscal sem aviso. Cópia vazia não impede o envio. O modal
de confirmação mostra `Para`/`Cópia` antes de disparar
(`GET /api/notificacoes/destinatarios?tipo=`) e a execução grava
`notificado_para`; sem isso, "quem recebeu o e-mail do processo 041?" não tem
resposta meses depois.

### Disponibilidade dos processos (ativo/inativo)

Um processo pode ser **desativado** em Configurações › Organização › Processos
(admin global). Inativo significa **não aceita novas execuções**:
`GET /api/modulos` o omite (o painel não o mostra) e
`POST /api/rateio/{tipo}/processar` responde **409**: a trava é no backend, não
só na tela. O que NÃO muda: o histórico das execuções antigas segue consultável
(são lançamentos que existiram no ERP), execuções já gravadas podem ser
concluídas (envio/notificação) e os cadastros continuam acessíveis ao admin, que
é onde se completa o que falta. O estado vive em `ProcessoStatus`
([models/processo.py](backend/app/models/processo.py)), com upsert na descoberta
do startup (rateio novo nasce ativo) e a regra única fica em
[services/processos.py](backend/app/services/processos.py). Admin é quem tem a
área `"*"`; as telas de Configurações chamam `GET /api/modulos?incluir_inativos=true`
para ainda enxergar o processo desativado.

## Como adicionar uma nova área / processo

A plataforma escala por **área → processos (rateios)**; adicionar uma área nova
(ex.: TI lançando linhas telefônicas) NÃO exige mudança estrutural:

1. **Criar o rateio (processo):** copie `app/modules/_template/` para um novo
   pacote e implemente (`tipo`, `nome`, `descricao`, `validar_inputs`,
   `processar`; e as capacidades `lanca_no_erp`/`notifica_fiscal` se lançar no
   ERP/notificar). O registry descobre no startup; nada mais no backend muda.
2. **Criar a área e vincular o processo:** em Configurações › Setores &
   Permissões, crie a área (ex.: "TI") e marque o novo rateio na **matriz
   Áreas × Rateios**. Isso grava em `AreaRateio` (via `PUT /organizacao/areas`).
3. **Dar acesso:** em Usuários, vincule os usuários à área com o nível
   (`operador` ou `admin da área`).

O `GET /api/modulos` já filtra por área, então a nova área só enxerga o seu
processo automaticamente. (Escopo mais fino, por centro de custo/departamento,
é uma camada futura; hoje `CentroCusto` não tem vínculo com área.)

## Convenções

- **Idioma**: todo texto de UI e a maior parte das docstrings/comentários são em
  **português brasileiro**. Identificadores de código em inglês (models,
  funções); nomes de domínio em português quando fazem parte do negócio.
- **Frontend**: Tailwind CSS v4 via `@tailwindcss/vite` (config em
  `vite.config.ts`, não em `tailwind.config.js`); classes utilitárias inline.
  Ícones `lucide-react` (única biblioteca de UI). Alias `@/` → raiz do frontend.
  Datas/moeda formatadas em `pt-BR`.
- **Backend**: SQLAlchemy 2.0 estilo `Mapped`/`mapped_column`. Migrações são
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` idempotentes em
  [migracoes.py](backend/app/db/migracoes.py) (não há Alembic). Regra de negócio
  fica nos `modules/`; routers ficam finos.

### Protheus: duas bases (LEITURA x ESCRITA)

A integração com o ERP é segregada por **eixo**, não por ambiente: por decisão de
projeto **consultamos a base oficial** (cadastro é dado real) e **escrevemos na base
de teste** até o go-live:

- `protheus_read_*`: consultas (colaboradores/dependentes). Base oficial.
- `protheus_write_*`: **toda** inclusão (AE, pré-nota e, quando o endpoint existir,
  a coparticipação por colaborador). Hoje a base de teste. O GET de contratos usa a
  base de ESCRITA de propósito: a AE referencia um contrato que precisa existir onde
  o título será gravado.

Nenhuma função pergunta "estou em teste?"; cada uma declara sua base
([protheus.py](backend/app/services/protheus.py)). **Go-live = só `.env`**: aponte
`PROTHEUS_WRITE_BASE_URL` para a base oficial, `PROTHEUS_WRITE_VERIFY_SSL=true` e
`PROTHEUS_WRITE_AMBIENTE=producao`. Os nomes antigos (`PROTHEUS_BASE_URL`,
`PROTHEUS_CONTRATOS_*`) seguem aceitos como alias.

O destino da escrita é visível em três pontos, e a subida é **recusada** em estados
incoerentes (rótulo "teste" escrevendo na base oficial; "producao" com SSL
desligado; ver `Settings._validar_base_de_escrita`):

1. log de subida com as duas bases ([main.py](backend/app/main.py));
2. auditoria por execução: `erp_ambiente`/`erp_base_url` em `EnvioErp` e
   `EnvioTentativa` distinguem título real de título de teste no histórico;
3. prefixo `[TESTE]` no assunto do e-mail ao fiscal enquanto não for produção.

**Colaboradores fictícios quando não há ERP (só a LEITURA)**: esta versão
pública roda sem Protheus por padrão (`PROTHEUS_READ_BASE_URL` vazia no
`.env.example`). Nesse caso, [routers/rateio.py](backend/app/routers/rateio.py)
usa `services/cadastro.carregar_colaboradores_demo` (tabela `ColaboradorDemo`,
semeada em [db/seed.py](backend/app/db/seed.py)) em vez de chamar
`protheus.listar_colaboradores`: mesmo formato de dict, os calculators
(coparticipação e mensalidade) não distinguem a origem. O gatilho é
EXCLUSIVAMENTE a URL vazia (ERP nunca configurado): uma falha de rede com o
ERP já configurado continua sendo `ProtheusError` → 502, nunca cai para o
cadastro fictício, pois misturar indisponibilidade real com dado de demonstração
seria perigoso. Não afeta a ESCRITA: "lançar no ERP" continua exigindo
`PROTHEUS_WRITE_BASE_URL` real. Ver [exemplos/](exemplos/) para uma planilha
de Consolidado que exercita esse cadastro.

## Segurança / produção (atenção)

Já resolvido (não reintroduza): `JWT_SECRET` e `POSTGRES_PASSWORD` são
**obrigatórios**: o `Settings` recusa a subida sem segredo de 32+ caracteres
(`_validar_jwt_secret`) e o compose usa `${POSTGRES_PASSWORD:?}`; o `.env` fica
fora das imagens (`.dockerignore` nos dois serviços); o backend roda como
usuário não-root; a porta 8000 só é publicada no loopback, pelo override de dev;
a rede `internal` tem subnet fixa (172.24.0.0/16), porque o sorteio do Docker já
colidiu com outras redes locais em hosts reais.

Pendente em dev: base de ESCRITA do Protheus em TESTE com
`PROTHEUS_WRITE_VERIFY_SSL=false` (cert self-signed) e HTTPS ainda desligado
(falta o certificado deste host).

## Versionamento

O repositório é versionado como **uma unidade** (backend e frontend sobem
juntos) via **semantic-release**, rodando **localmente**; não há CI.
Configuração em [.releaserc.json](.releaserc.json); o `package.json` da raiz
existe só para hospedar a versão e o ferramental (os serviços não ganham
dependências com isso).

```bash
npm install            # uma vez, na raiz
npm run release:dry    # mostra a próxima versão e as notas, sem escrever nada
npm run release        # semantic-release --no-ci
```

- **Branch de release: `main`**: é ela que o host de produção clona. `develop`
  segue sendo a branch de trabalho. O fluxo é: integrar em `develop` → merge em
  `main` → `npm run release` em `main` → **merge de `main` de volta em
  `develop`**, para o commit `chore(release)` e a tag existirem nas duas (sem
  isso o cálculo da próxima versão divergiria entre as branches).
- **Requer Node ≥ 22.22.2** (piso dos plugins `git@11`/`changelog@7`). É só para
  a ferramenta de release; os containers seguem com as suas próprias imagens.
- `npm run release` faz tudo em uma operação: calcula a versão, escreve o
  `CHANGELOG.md`, propaga a versão para os quatro pontos (raiz,
  `frontend/package.json`, `backend/pyproject.toml` e `backend/app/version.py`),
  commita como `chore(release): x.y.z [skip ci]`, cria a tag `vx.y.z` e dá push.
  **Depois dele o `git status` fica limpo**: não commite nada à mão.
- **Não editar `CHANGELOG.md` à mão** (é reescrito a cada release), **não criar
  tags manualmente** e **não fazer force-push em `main`**: qualquer um dos três
  quebra o cálculo da próxima versão.
- `conventional-changelog-conventionalcommits` está pinado em **`^9.x`** de
  propósito: a v10 exige `conventional-changelog-writer@9+`, e o
  `@semantic-release/release-notes-generator@14` embute o `writer@8`.

### A versão do backend é Python, não npm

Não há `backend/package.json` para o `npm version` bumpar. O `prepareCmd` do
`@semantic-release/exec` reescreve dois arquivos:
`[project].version` do [pyproject.toml](backend/pyproject.toml) (metadado) e
[app/version.py](backend/app/version.py) via
[scripts/escreve-versao-backend.sh](scripts/escreve-versao-backend.sh): este é
a fonte consultada em **runtime**, por `FastAPI(version=...)`, pelo log de
subida e por `GET /api/health` (`{"status": "ok", "versao": "x.y.z"}`, que é
como se confere qual release está no ar sem abrir o container). **Nenhum dos
dois se edita à mão.**

No frontend, a versão é injetada em **build-time** (`__APP_VERSION__`, definido
no [vite.config.ts](frontend/vite.config.ts) a partir do `package.json`) e
aparece no rodapé da [Sidebar](frontend/src/components/Sidebar.tsx). Como é
build-time, **trocar de versão só muda a tela depois de
`docker compose build frontend`**; restart não basta.

### Conventional Commits: efeito na versão

| Prefixo | Versão | CHANGELOG |
|---|---|---|
| `fix:` | patch (x.y.**Z**) | Correções |
| `feat:` | minor (x.**Y**.0) | Funcionalidades |
| `perf:` | patch | Performance |
| `refactor:` | patch | Refatorações |
| `docs:` `chore:` `style:` `test:` `build:` `ci:` | nenhuma | oculto |
| `feat!:` ou rodapé `BREAKING CHANGE:` | major (**X**.0.0) | Breaking changes |

Vence sempre o maior bump entre os commits acumulados. Escopo é opcional e
aparece em negrito no changelog: `feat(coparticipacao): ...`. A partir da
`1.0.0` o breaking change é legítimo: use-o quando a mudança exigir ação de
quem opera (ex.: variável de `.env` renomeada, formato de arquivo de entrada
alterado), não para refatoração interna.

## Dois hosts, um repositório

Produção roda em host **segregado**, a partir do mesmo repositório: lá é
`git clone` + preencher os dois `.env` (raiz e `backend/`), sem editar arquivo
versionado. Nada de ambiente mora em arquivo versionado.

| | dev (vm-dev, 203.0.113.20) | produção (host próprio) |
|---|---|---|
| domínio | `dev.financeflow.example.com` | `financeflow.example.com` |
| `ENV_PREFIX` | `dev` | `prod` |
| usuários de teste do seed | criados | **não** criados |
| base de ESCRITA do ERP | teste | oficial |

- **HTTPS é o padrão nos dois hosts**, sem variável e sem arquivo extra: o router
  `websecure` serve a aplicação e o router `web` **sempre** redireciona (301). O
  certificado vem da **CA do AD Windows** (`CA-DEMO-01`), não de ACME:
  converta o `.pfx` para `.crt`/`.key`, coloque em
  `/opt/docker/app-traefik/certs/` do host e declare em `dynamic/tls-certs.yml`
  (o provider tem `watch`, não precisa reiniciar o Traefik). Um certificado por
  host; segregados não compartilham chave privada. `FRONTEND_CERTRESOLVER` fica
  **vazio**: é isso que faz o Traefik usar o certificado do store em vez de
  tentar emitir um. Enquanto um host não tiver o seu, o Traefik serve o
  certificado padrão do store e o navegador acusa nome incorreto; a aplicação
  funciona ao aceitar a exceção (não enviamos HSTS). Nunca emita a label
  `tls.certresolver` num router de entrypoint `web`: ela liga TLS, o router para
  de casar e o Traefik responde 404 sem router no log.
- **Nada de ambiente em arquivo versionado.** O `docker-compose.yml` é idêntico
  nos dois hosts; o que difere vive no `.env` (domínio, prefixo, senha, subnet).
  Editar o compose num host cria divergência que o próximo `git pull` reclama.
  A exceção é o `docker-compose.override.yml`: é versionado, mas é **exclusivo
  de host sem Traefik** (ver "Rodar sem o Traefik" acima); em dev/produção ele
  precisa estar ausente (apagado ou renomeado) antes do primeiro `docker
  compose up`, senão remove o roteamento e o TLS do Traefik nesses hosts.
- **Admin inicial**: `SEED_ADMIN_EMAIL`/`SEED_ADMIN_SENHA`/`SEED_ADMIN_NOME` no
  `backend/.env`, usados só quando o banco está vazio. Em produção (`APP_ENV=prod`,
  derivado do `ENV_PREFIX`) o seed **recusa subir** com banco vazio e sem admin
  definido, em vez de criar `admin/admin`; e os usuários de teste (`admin`, `rh`,
  `operador`) só existem fora de produção.
- **Levar os cadastros para o host novo**: [scripts/dump-cadastros.sh](scripts/dump-cadastros.sh)
  gera um dump `--data-only` só das tabelas de cadastro (áreas, usuários,
  empresas, fornecedores, centros de custo, PJ, faixas, parâmetros, linhas,
  notificações). Execuções, documentos e envios ficam de fora de propósito: são
  lançamentos feitos na base de TESTE do ERP e contaminariam o histórico oficial.

