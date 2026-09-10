"""
Configurações da aplicação, carregadas a partir de variáveis de ambiente / .env.

Usa `pydantic-settings` para ler e validar as variáveis de forma tipada.
Em produção, as variáveis vêm do ambiente (docker-compose / orquestrador);
em desenvolvimento, de um arquivo `.env` na raiz do backend.

Ver `.env.example` para a lista de variáveis suportadas.
"""

import re
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Ambientes válidos da base de ESCRITA (rótulo declarado no .env).
AMBIENTES_ESCRITA = ("teste", "producao")


def _destino(url: str) -> str:
    """host:porta de uma base (identidade do ambiente), ignorando esquema e path."""
    return urlsplit((url or "").strip().rstrip("/")).netloc.lower()


class Settings(BaseSettings):
    """
    Modelo tipado das configurações da plataforma.

    Cada atributo corresponde a uma variável de ambiente (case-insensitive).
    Valores definidos aqui são os defaults usados quando a variável não está
    presente no ambiente nem no `.env`.
    """

    # --- Identificação contábil (Protheus) ---
    # Empresa e filial usadas nos lançamentos de rateio.
    # TODO: estes valores alimentarão a integração real com o Protheus.
    empresa: str = ""
    filial: str = ""

    # --- API Protheus: base de LEITURA (consultas) ---
    # A segregação das bases é por EIXO — leitura x escrita —, não por "ambiente":
    # por decisão de projeto CONSULTAMOS a base oficial (cadastro é dado real) e
    # ESCREVEMOS na base de teste até o go-live. Ver o bloco de escrita abaixo.
    # A URL de cada empresa é concatenada como {base}/{rest}/{path}.
    # Aceita PROTHEUS_BASE_URL (nome antigo) para não quebrar .env em uso.
    protheus_read_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("protheus_read_base_url", "protheus_base_url"),
    )
    protheus_colaboradores_path: str = "uapi001/lista-colaboradores"
    # Mapa rest -> empresa (rótulo usado no rateio). Lido de PROTHEUS_RESTS (JSON).
    # Ajuste os rests/rótulos conforme o ambiente Protheus.
    protheus_rests: dict[str, str] = {
        "rest01": "Aurora",
        "rest02": "Vertex",
        "rest15": "Zenith",
    }
    # Rests a consultar POR RATEIO (rest keys). Rateio não listado -> TODOS os rests.
    # Unimed fatura apenas Vertex + Zenith (Aurora não é faturado pela Unimed) e
    # a Aurora traz registros "casca" (classe de valor vazia) que poluem o dedup.
    # A coparticipação (desconto em folha) também exclui a Aurora: não há colaborador
    # ATIVO lá, e as cascas criavam empate no dedup por CPF (mesmo salário em três
    # empresas), o que jogava a pessoa para tratativa manual sem necessidade.
    protheus_rests_por_tipo: dict[str, list[str]] = {
        "pagamento-unimed": ["rest02", "rest15"],
        "pagamento-coparticipacao-unimed": ["rest02", "rest15"],
        "coparticipacao-plano-saude": ["rest02", "rest15"],
    }
    # Autenticação da LEITURA: basic (user/senha) OU token Bearer (se informado,
    # prevalece). A escrita herda estas credenciais se não tiver as suas.
    protheus_user: str = ""
    protheus_password: str = ""
    protheus_token: str = ""
    # Rede da leitura. Paginação usa o parâmetro nPage (ver services/protheus.py).
    protheus_read_timeout: int = Field(
        default=30,
        validation_alias=AliasChoices("protheus_read_timeout", "protheus_timeout"),
    )
    protheus_read_verify_ssl: bool = Field(
        default=True,
        validation_alias=AliasChoices("protheus_read_verify_ssl", "protheus_verify_ssl"),
    )

    # --- API Protheus: base de ESCRITA (inclusões) ---
    # TODA inclusão vai para esta base: Autorização de Entrega, pré-nota e (quando
    # o endpoint estiver definido) a coparticipação por colaborador. Hoje aponta
    # para a base de TESTE.
    #
    # GO-LIVE = só .env, sem tocar em código: aponte PROTHEUS_WRITE_BASE_URL para a
    # base oficial, defina PROTHEUS_WRITE_VERIFY_SSL=true e troque o rótulo
    # PROTHEUS_WRITE_AMBIENTE para "producao". Estado incoerente (ex.: escrever na
    # base de leitura ainda rotulado "teste") NÃO impede a aplicação de subir: é
    # avisado no log e bloqueia só o POST no ERP (ver `problemas_escrita`).
    #
    # Aceita PROTHEUS_CONTRATOS_* (nomes antigos) para não quebrar .env em uso.
    # O rest vai na URL e define a empresa (rest02=Vertex, rest15=Zenith).
    protheus_write_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("protheus_write_base_url", "protheus_contratos_base_url"),
    )
    # Rótulo do ambiente de escrita: "teste" | "producao". NÃO muda comportamento de
    # rede — só torna o destino visível (log de subida, auditoria da execução, badge
    # na UI e prefixo [TESTE] no e-mail ao fiscal).
    protheus_write_ambiente: str = "teste"
    # Credenciais próprias da base de escrita. Vazias -> herda as de leitura.
    protheus_write_user: str = ""
    protheus_write_password: str = ""
    protheus_write_token: str = ""
    # GET: contratos de parceria disponíveis (param cCGCFornecedor = CNPJ do fornecedor).
    # Fica na base de ESCRITA de propósito: a AE referencia o C3_NUM do contrato, que
    # precisa existir na mesma base onde o título será gravado.
    protheus_contratos_path: str = "api/com/v1/partnership-agreement"
    # POST: inclui a Autorização de Entrega (gera o título), referenciando o contrato.
    protheus_ae_path: str = "api/com/v1/delivery-authorization"
    # POST: pré-nota (entrada de nota) — rotina das empresas "pre_nota" (Zenith).
    # Não usa contrato; o produto é fixo (não há item de contrato para herdar).
    protheus_prenota_path: str = "api/com/v1/incoming-pro-forma-invoice"
    # POST: coparticipação por colaborador (desconto em folha; rotina GPE). NÃO gera
    # título — inclui o registro de desconto na folha de cada matrícula.
    protheus_coparticipacao_path: str = "api/gpe/v1/co-participation"
    protheus_prenota_produto: str = "400366"
    protheus_prenota_filial: str = "01"
    # Verificação SSL da base de escrita. Default False porque a base de TESTE usa
    # certificado self-signed. Na base OFICIAL, use true (a validação exige).
    protheus_write_verify_ssl: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "protheus_write_verify_ssl", "protheus_contratos_verify_ssl"
        ),
    )
    # Timeout (s) da base de escrita. Maior que o de leitura porque a inclusão
    # ESCREVE no ERP (gera o título) e pode demorar.
    protheus_write_timeout: int = Field(
        default=120,
        validation_alias=AliasChoices("protheus_write_timeout", "protheus_contratos_timeout"),
    )
    # CNPJ (só dígitos) do FORNECEDOR (operadora) por rateio — usado em cCGCFornecedor.
    protheus_fornecedor_cnpj: dict[str, str] = {
        "unimed": "45678910000166",
        "bradesco": "56789120000174",
        "claro": "67891230000169",
    }
    # Telefonia: todos os boletos são lançados numa única empresa (decisão do
    # negócio), então a AE da Claro não varre empresas como o plano de saúde.
    protheus_claro_empresa: str = "Vertex"
    # Rotina de lançamento no ERP por empresa. Empresa não listada -> "ae"
    # (Autorização de Entrega). Zenith usa "pre_nota" (endpoint em preparação).
    protheus_rotina_por_empresa: dict[str, str] = {"Zenith": "pre_nota"}

    # --- SMTP (notificação ao dep. fiscal) ---
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""            # remetente; se vazio, usa smtp_user
    smtp_tls: bool = True          # STARTTLS (587). Para SSL puro (465), use smtp_ssl.
    smtp_ssl: bool = False
    # Destinatários do dep. fiscal (separados por vírgula). Ex.: "fiscal@x.com, y@x.com".
    fiscal_emails: str = ""

    def lista_fiscal(self) -> list[str]:
        return [e.strip() for e in self.fiscal_emails.split(",") if e.strip()]

    # --- Autenticação (login + segregação por área) ---
    # Sem default: um default conhecido em campo de segredo permite forjar token
    # em qualquer instalação que esqueça de trocá-lo. A ausência é recusada na
    # subida (ver `_validar_jwt_secret`).
    jwt_secret: str = ""
    jwt_algoritmo: str = "HS256"
    jwt_expira_min: int = 480  # validade do token (min); 480 = 8h

    # --- Banco de dados ---
    # Sobreposta pelo docker-compose (aponta para o serviço `postgres`).
    database_url: str = "postgresql+psycopg://financeflow:financeflow@postgres:5432/financeflow"

    # --- Ambiente desta instância ---
    # Vem do `ENV_PREFIX` do compose (dev | hml | prod). Default de PRODUÇÃO, para
    # que um .env incompleto não habilite comportamento de desenvolvimento por
    # omissão. Hoje decide se os usuários de teste do seed são criados.
    app_env: str = "prod"

    @property
    def producao(self) -> bool:
        return self.app_env.strip().lower() in ("prod", "producao", "production")

    # --- Administrador inicial (instalação nova) ---
    # Usado pelo seed SOMENTE quando não existe nenhum usuário no banco. Sem
    # isso, um host novo nasce com as credenciais de teste que estão no código.
    seed_admin_email: str = ""
    seed_admin_senha: str = ""
    seed_admin_nome: str = "Administrador"

    # --- CORS ---
    # Origens autorizadas a consumir a API. O frontend é servido na MESMA origem
    # (o nginx faz proxy de /api/), então isto vale para chamadas diretas à API:
    # o dev server do vite e ferramentas de diagnóstico.
    #
    # É TEXTO (lista separada por vírgula), não `list[str]`: para campos de tipo
    # complexo o pydantic-settings exige JSON na variável de ambiente e falha na
    # própria fonte, ANTES de qualquer validador — `CORS_ORIGINS=https://x.com`
    # derrubava a subida com "error parsing value for field". Mesmo padrão de
    # `fiscal_emails`, que já era texto com um helper de leitura.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    def lista_cors(self) -> list[str]:
        """Origens do CORS. Tolera vírgula, ponto e vírgula e formato JSON."""
        bruto = self.cors_origins.strip().strip("[]")
        return [v.strip().strip("\"'") for v in re.split(r"[;,]", bruto) if v.strip().strip("\"'")]

    # Configuração de carregamento: lê do arquivo .env, ignora variáveis extras.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Campos com validation_alias também aceitam o próprio nome (útil em
        # Settings(protheus_write_base_url=...) nos testes/scripts).
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def _validar_jwt_secret(self) -> "Settings":
        """
        Recusa a subida sem segredo de JWT (ou com segredo curto).

        Equivalente do `config/secrets.ts` das apps Node: falhar aqui é ruidoso e
        acontece uma vez, no deploy. Rodar com o default de desenvolvimento é
        silencioso e vale para sempre.
        """
        if len(self.jwt_secret.strip()) < 32:
            raise ValueError(
                "JWT_SECRET ausente ou curto (mínimo 32 caracteres) — defina no "
                ".env do backend. Gere com: openssl rand -hex 48"
            )
        return self

    @model_validator(mode="after")
    def _normalizar_ambiente_escrita(self) -> "Settings":
        """Normaliza o rótulo do ambiente (aparas/caixa). NÃO recusa nada aqui.

        Config incoerente NÃO pode impedir a aplicação de subir: quem depende dela
        é só a inclusão no ERP, e derrubar o processo tirava o login (e tudo o mais)
        do ar por um erro de digitação no `.env`. A coerência é verificada em
        `problemas_escrita()`, avisada no log de subida e cobrada no momento do POST.
        """
        self.protheus_write_ambiente = (self.protheus_write_ambiente or "").strip().lower()
        return self

    def problemas_escrita(self) -> list[str]:
        """
        Incoerências que tornam a ESCRITA no ERP insegura. Vazio = pode gravar.

        1) rótulo inválido (ex.: "prod", "produção"): um rótulo errado desliga
           silenciosamente o [TESTE] do e-mail fiscal e a marcação na UI.
        2) rótulo "producao" com SSL desligado: na base oficial o certificado é
           válido; verify=false indica URL de teste ou verificação desativada em
           escrita real.
        3) escrever na MESMA base de onde se lê, ainda rotulado "teste": é o erro
           perigoso — lançamento real tratado como teste.
        """
        problemas: list[str] = []
        ambiente = self.protheus_write_ambiente
        if ambiente not in AMBIENTES_ESCRITA:
            problemas.append(
                f"PROTHEUS_WRITE_AMBIENTE inválido: {ambiente!r}. "
                f"Use um de: {', '.join(AMBIENTES_ESCRITA)}."
            )
        if ambiente == "producao" and not self.protheus_write_verify_ssl:
            problemas.append(
                "PROTHEUS_WRITE_AMBIENTE=producao exige PROTHEUS_WRITE_VERIFY_SSL=true "
                "(a base oficial tem certificado válido; verify=false indica que a URL "
                "de escrita ainda é a de teste)."
            )
        leitura, escrita = _destino(self.protheus_read_base_url), _destino(self.protheus_write_base_url)
        if escrita and escrita == leitura and ambiente != "producao":
            problemas.append(
                f"PROTHEUS_WRITE_BASE_URL aponta para a MESMA base da leitura ({escrita}) "
                f"mas PROTHEUS_WRITE_AMBIENTE={ambiente!r}. Se a escrita já é em produção, "
                "defina PROTHEUS_WRITE_AMBIENTE=producao; senão, corrija a URL de escrita."
            )
        return problemas

    @property
    def escrita_em_producao(self) -> bool:
        """True quando as inclusões vão para a base oficial (rótulo "producao")."""
        return self.protheus_write_ambiente == "producao"

    def credenciais_escrita(self) -> tuple[str, str, str]:
        """(user, senha, token) da base de escrita; sem as suas, herda a leitura."""
        if self.protheus_write_token or self.protheus_write_user:
            return (
                self.protheus_write_user,
                self.protheus_write_password,
                self.protheus_write_token,
            )
        return (self.protheus_user, self.protheus_password, self.protheus_token)

    def rests_do_tipo(self, tipo: str) -> dict[str, str]:
        """Rests (rest -> empresa) a consultar para um rateio. Sem mapeamento -> todos."""
        permitidos = self.protheus_rests_por_tipo.get(tipo)
        if not permitidos:
            return self.protheus_rests
        return {r: e for r, e in self.protheus_rests.items() if r in permitidos}

    def rest_da_empresa(self, empresa: str) -> str | None:
        """Rest (ex.: 'rest02') correspondente ao rótulo de empresa (ex.: 'Vertex')."""
        alvo = (empresa or "").strip().upper()
        for rest, nome in self.protheus_rests.items():
            if nome.strip().upper() == alvo:
                return rest
        return None

    def rotina_erp(self, empresa: str) -> str:
        """Rotina de lançamento no ERP da empresa: 'ae' (padrão) ou 'pre_nota'."""
        alvo = (empresa or "").strip().lower()
        for nome, rotina in self.protheus_rotina_por_empresa.items():
            if nome.strip().lower() == alvo:
                return rotina
        return "ae"


@lru_cache
def get_settings() -> Settings:
    """
    Retorna a instância única (cacheada) de Settings.

    O `lru_cache` garante que o `.env` seja lido uma só vez por processo.
    Use esta função (e não `Settings()` diretamente) em todo o código,
    inclusive como dependência do FastAPI via `Depends(get_settings)`.
    """
    return Settings()
