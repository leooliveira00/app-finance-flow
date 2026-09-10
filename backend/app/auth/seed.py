"""
Seed de usuários e do mapa área↔rateios (configuração inicial).

TRANSITÓRIO: hoje é um seed em código. Migra para Postgres + telas de cadastro
(usuários, áreas, permissões) numa fase seguinte, sem mudar a interface de
`service.py`.

As senhas ficam em texto AQUI apenas para facilitar o ajuste em dev; são
convertidas para hash bcrypt na carga (ver `service._user_store`). NÃO use este
seed como está em produção — troque por cadastro real e senhas fortes.
"""

# Usuários iniciais.
# - `areas` contendo "*" => admin GLOBAL (enxerga todos os rateios; sem nível por área).
# - `niveis` mapeia {área: nivel} para não-admins: "operador" ou "admin_area".
#   Área sem nível declarado assume "operador".
USUARIOS_SEED: list[dict] = [
    {"email": "admin@financeflow.local", "senha": "admin", "nome": "Administrador", "areas": ["*"]},
    # admin_area do RH: audita salário/teto e edita o cadastro do RH.
    {"email": "rh@financeflow.local", "senha": "rh", "nome": "RH (admin da área)",
     "areas": ["RH"], "niveis": {"RH": "admin_area"}},
    # operador do RH: opera e envia ao ERP, sem ver salário/teto.
    {"email": "operador@financeflow.local", "senha": "operador", "nome": "RH (operador)",
     "areas": ["RH"], "niveis": {"RH": "operador"}},
]

# Cadastro (migrado para o Postgres via db/seed): área -> tipos de rateio.
AREAS_RATEIOS: dict[str, list[str]] = {
    "RH": [
        "pagamento-unimed",
        "pagamento-bradesco",
        "pagamento-coparticipacao-unimed",
        "coparticipacao-plano-saude",
    ],
}
