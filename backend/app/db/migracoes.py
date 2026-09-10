"""
Migrações leves e idempotentes (sem Alembic).

`Base.metadata.create_all` cria tabelas que faltam, mas NÃO adiciona colunas a
tabelas já existentes. Para colunas novas em tabelas antigas usamos
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (Postgres), seguro para rodar sempre
no startup.
"""

from sqlalchemy import text
from sqlalchemy.engine import Engine

# (tabela, coluna, definição DDL) — todas idempotentes.
_COLUNAS = [
    ("colaborador_pj", "centro_custo", "VARCHAR(60) NOT NULL DEFAULT ''"),
    ("colaborador_pj", "empresa", "VARCHAR(120) NOT NULL DEFAULT ''"),
    ("colaborador_pj", "classe_valor", "VARCHAR(60) NOT NULL DEFAULT ''"),
    ("execucao", "notificado_em", "TIMESTAMPTZ"),
    # Nível do usuário por área (operador | admin_area). Bancos antigos tinham
    # a associação sem nível — o default cobre os vínculos já existentes.
    ("usuario_area", "nivel", "VARCHAR(20) NOT NULL DEFAULT 'operador'"),
    # Login por e-mail (substitui o antigo `username`). Coluna adicionada sem
    # unique aqui; o índice único e o backfill vêm em _STATEMENTS.
    ("usuario", "email", "VARCHAR(120)"),
    # Conta Claro à qual a linha telefônica está vinculada (confere o boleto).
    ("linha_telefonica", "conta", "VARCHAR(30) NOT NULL DEFAULT ''"),
    # Onde o lançamento foi gravado (base de ESCRITA do Protheus no momento do
    # envio). Sem isto, após o go-live não há como distinguir no histórico um
    # título real de um gravado na base de teste. Linhas antigas ficam vazias —
    # são, por definição, do período em que só existia base de teste.
    ("envio_erp", "erp_ambiente", "VARCHAR(20) NOT NULL DEFAULT ''"),
    ("envio_erp", "erp_base_url", "VARCHAR(255) NOT NULL DEFAULT ''"),
    ("envio_tentativa", "erp_ambiente", "VARCHAR(20) NOT NULL DEFAULT ''"),
    ("envio_tentativa", "erp_base_url", "VARCHAR(255) NOT NULL DEFAULT ''"),
    # Telefonia: um título por BOLETO na mesma empresa — a referência (conta da
    # Claro) completa a chave do envio e da trava de reenvio.
    ("envio_erp", "referencia", "VARCHAR(60) NOT NULL DEFAULT ''"),
    ("envio_tentativa", "referencia", "VARCHAR(60) NOT NULL DEFAULT ''"),
    # Cópia das notificações por ÁREA (a área é dona dos processos).
    ("area", "emails_copia", "VARCHAR(500) NOT NULL DEFAULT ''"),
    # Destinatários efetivamente usados na notificação da execução.
    ("execucao", "notificado_para", "JSONB"),
    # Envio parcial (lote da folha): contagens e matrículas a reenviar.
    ("envio_erp", "enviados", "INTEGER NOT NULL DEFAULT 0"),
    ("envio_erp", "aceitos", "INTEGER NOT NULL DEFAULT 0"),
    ("envio_erp", "matriculas_pendentes", "JSONB"),
    # Resposta bruta do ERP na tentativa que falhou (diagnóstico do 200 parcial).
    ("envio_tentativa", "resposta_erp", "JSONB"),
]

# Statements SQL idempotentes rodados APÓS o ADD COLUMN. Ordem importa.
_STATEMENTS = [
    # Migração de identidade username -> email. O backfill só roda se `username`
    # ainda existir (em banco novo o create_all já cria só com `email`, então o
    # bloco vira no-op). Deriva o e-mail do login antigo (admin -> admin@...).
    """
    DO $$ BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'usuario' AND column_name = 'username'
      ) THEN
        UPDATE usuario
           SET email = lower(username) || '@financeflow.local'
         WHERE email IS NULL OR email = '';
      END IF;
    END $$;
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_usuario_email ON usuario (email)",
    "ALTER TABLE usuario DROP COLUMN IF EXISTS username",
    # operadora -> fornecedor: a entidade sempre foi "quem recebe o título no
    # ERP"; o nome antigo descrevia só o plano de saúde e não cabia na telefonia.
    # O `create_all` já criou `fornecedor` vazia, então aqui copiamos as linhas e
    # descartamos a tabela antiga (idempotente: no-op se `operadora` não existe).
    """
    DO $$ BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = 'operadora'
      ) THEN
        INSERT INTO fornecedor (nome, cnpj)
             SELECT nome, cnpj FROM operadora
          ON CONFLICT (nome) DO NOTHING;
        DROP TABLE operadora;
      END IF;
    END $$;
    """,
    # tipo_doc da operadora era decorativo (nada consumia) — removido.
    "ALTER TABLE fornecedor DROP COLUMN IF EXISTS tipo_doc",
    # fornecedor_cnpj era o MESMO CNPJ do fornecedor, só em dígitos — colapsado no
    # campo `cnpj` (os dígitos p/ o ERP são derivados em código).
    "ALTER TABLE fornecedor DROP COLUMN IF EXISTS fornecedor_cnpj",
]


def aplicar_migracoes(engine: Engine) -> None:
    with engine.begin() as conn:
        for tabela, coluna, ddl in _COLUNAS:
            conn.execute(
                text(f'ALTER TABLE {tabela} ADD COLUMN IF NOT EXISTS {coluna} {ddl}')
            )
        for stmt in _STATEMENTS:
            conn.execute(text(stmt))
