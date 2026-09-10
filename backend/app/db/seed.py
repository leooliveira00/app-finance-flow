"""
Seed inicial (idempotente) do Postgres.

Migra para o banco os seeds que estavam em código:
- Usuários e áreas (de `app.auth.seed`).
- Consenso da coparticipação (faixas × tipo → valor) + teto, definido aqui.

Idempotente: só popula tabelas vazias. Chamado no startup após criar o schema.
O de-para de empresas (validators) ainda NÃO é migrado aqui (fica em config por
enquanto; entra numa etapa seguinte).
"""

import csv
from decimal import Decimal
from pathlib import Path

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.seed import AREAS_RATEIOS, USUARIOS_SEED
from app.config import get_settings
from app.models.auth import NIVEL_OPERADOR, Area, AreaRateio, Usuario, UsuarioArea
from app.models.colaborador_demo import ColaboradorDemo
from app.models.coparticipacao import (
    FaixaCoparticipacao,
    ParametroRateio,
    ValorCoparticipacao,
)
from app.models.organizacao_fiscal import Empresa, Fornecedor
from app.models.pagamento import CentroCusto

# Carga inicial das EMPRESAS (migra config.protheus_rests + rotina_por_empresa +
# prenota_* e validators._EMPRESAS_POR_CNPJ). (nome, rest, cnpj, rotina, produto, filial)
EMPRESAS_SEED: list[tuple[str, str, str, str, str, str]] = [
    ("Aurora", "rest01", "12.345.670/0001-29", "ae", "", ""),
    ("Vertex", "rest02", "23.456.780/0001-84", "ae", "", ""),
    ("Zenith", "rest15", "34.567.890/0001-30", "pre_nota", "400366", "01"),
]

# Carga inicial dos FORNECEDORES (migra validators._CNPJ_UNIMED/_BRADESCO). O
# `nome` é a chave que o módulo declara em `RateioModule.fornecedor`; o CNPJ é
# único (formatado) e os dígitos p/ o ERP são derivados. (nome, cnpj)
FORNECEDORES_SEED: list[tuple[str, str]] = [
    ("unimed", "45.678.910/0001-66"),
    ("bradesco", "56.789.120/0001-74"),
    # Telefonia (rateio das faturas da Claro).
    ("claro", "67.891.230/0001-69"),
]

# CSV de carga inicial dos centros de custo (Codigo;Nome), enviado pelo cliente.
_CSV_CENTROS_CUSTO = Path(__file__).resolve().parent / "seeds" / "centros_custo.csv"

# Colaboradores FICTÍCIOS (substituem o Protheus quando PROTHEUS_READ_BASE_URL
# está vazia — ver ColaboradorDemo e services/cadastro.carregar_colaboradores_demo).
# CPFs e cenários casam com `exemplos/consolidado_coparticipacao_unimed.xlsx`:
# (cpf, nome, salario, matricula, filial, empresa, situacao)
# - Ana Beatriz Souza / Carlos Eduardo Lima / Juliana Martins Pereira: itens normais.
# - Fernanda Ribeiro Alves: salário baixo com muitos eventos -> estoura o teto.
# - Roberto Nunes Costa: DEMITIDO -> divergência "colaborador desligado".
# - O CPF 555.666.777-20 (Marcos Vinícius Teixeira) É DE PROPÓSITO ausente daqui:
#   demonstra a divergência "titular não encontrado".
COLABORADORES_DEMO_SEED: list[tuple[str, str, str, str, str, str, str]] = [
    ("11122233396", "Ana Beatriz Souza", "3200.00", "1001", "01", "Vertex", "ATIVO"),
    ("22233344405", "Carlos Eduardo Lima", "8500.00", "1002", "01", "Vertex", "ATIVO"),
    ("33344455508", "Fernanda Ribeiro Alves", "1300.00", "2001", "15", "Zenith", "ATIVO"),
    ("44455566619", "Roberto Nunes Costa", "5200.00", "1004", "01", "Vertex", "DEMITIDO"),
    ("66677788830", "Juliana Martins Pereira", "15000.00", "1006", "01", "Vertex", "ATIVO"),
]

# Consenso da coparticipação: (nome, sal_inicial, sal_final, {tipo: valor}).
CONSENSO_SEED: list[tuple[str, str, str, dict[str, str]]] = [
    ("Faixa 0", "0.00", "1299.99", {"consulta": "0.00", "simples": "0.00", "especial": "0.00"}),
    ("Faixa 1", "1300.00", "2499.99", {"consulta": "10.00", "simples": "2.00", "especial": "5.00"}),
    ("Faixa 2", "2500.00", "4449.99", {"consulta": "13.90", "simples": "3.56", "especial": "8.90"}),
    ("Faixa 3", "4450.00", "6999.99", {"consulta": "17.88", "simples": "5.60", "especial": "13.99"}),
    ("Faixa 4", "7000.00", "9999.99", {"consulta": "21.71", "simples": "8.00", "especial": "19.99"}),
    ("Faixa 5", "10000.00", "13999.99", {"consulta": "26.05", "simples": "11.19", "especial": "27.98"}),
    ("Faixa 6", "14000.00", "9999999999.99", {"consulta": "31.00", "simples": "15.45", "especial": "37.62"}),
]

TETO_PERCENTUAL_COPART = "20"
SALARIO_PADRAO_PJ = "10000"  # PJ usa a penúltima faixa (10k–13.999,99)


def _hash(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


def _seed_parametros(db: Session) -> None:
    if db.get(ParametroRateio, "teto_percentual_copart") is None:
        db.add(
            ParametroRateio(
                chave="teto_percentual_copart",
                valor=TETO_PERCENTUAL_COPART,
                descricao="Teto do desconto de coparticipação (% do salário).",
            )
        )
    if db.get(ParametroRateio, "salario_padrao_pj") is None:
        db.add(
            ParametroRateio(
                chave="salario_padrao_pj",
                valor=SALARIO_PADRAO_PJ,
                descricao="Salário padrão de colaboradores PJ (define a faixa; penúltima).",
            )
        )


def _seed_consenso(db: Session) -> None:
    if db.scalar(select(FaixaCoparticipacao.id).limit(1)) is not None:
        return
    for ordem, (nome, ini, fim, valores) in enumerate(CONSENSO_SEED):
        faixa = FaixaCoparticipacao(
            nome=nome,
            salario_inicial=Decimal(ini),
            salario_final=Decimal(fim),
            ordem=ordem,
            valores=[
                ValorCoparticipacao(tipo=tipo, valor=Decimal(valor))
                for tipo, valor in valores.items()
            ],
        )
        db.add(faixa)


def _seed_usuarios_areas(db: Session) -> None:
    if db.scalar(select(Usuario.id).limit(1)) is not None:
        return

    settings = get_settings()

    # Áreas + seus rateios (do mapa AREAS_RATEIOS).
    areas: dict[str, Area] = {}
    for nome_area, tipos in AREAS_RATEIOS.items():
        area = Area(nome=nome_area, rateios=[AreaRateio(tipo=t) for t in tipos])
        areas[nome_area] = area
        db.add(area)

    # Admin inicial do .env: é o que permite entrar num host novo sem depender
    # das credenciais de teste. Só entra se houver e-mail E senha definidos.
    email_admin = settings.seed_admin_email.strip().lower()
    senha_admin = settings.seed_admin_senha
    if email_admin and senha_admin:
        db.add(
            Usuario(
                email=email_admin,
                nome=settings.seed_admin_nome.strip() or "Administrador",
                senha_hash=_hash(senha_admin),
                admin=True,
                area_links=[],
            )
        )

    # Usuários de TESTE (admin/admin, rh/rh, operador/operador): só fora de
    # produção. Num host de produção eles seriam uma porta aberta com senha
    # conhecida — por isso o `app_env` tem default de produção.
    if settings.producao:
        if not (email_admin and senha_admin):
            raise RuntimeError(
                "Banco vazio em produção e nenhum administrador definido: "
                "informe SEED_ADMIN_EMAIL e SEED_ADMIN_SENHA no .env do backend."
            )
        return

    # Usuários (senha em hash). "*" nas áreas => admin global (vê tudo, sem nível).
    # Não-admins recebem vínculos usuario_area com o nível de `niveis` (default operador).
    for usuario in USUARIOS_SEED:
        if usuario["email"].strip().lower() == email_admin:
            continue  # já criado a partir do .env
        eh_admin = "*" in usuario["areas"]
        niveis = usuario.get("niveis", {})
        links = (
            []
            if eh_admin
            else [
                UsuarioArea(area=areas[a], nivel=niveis.get(a, NIVEL_OPERADOR))
                for a in usuario["areas"]
                if a in areas
            ]
        )
        db.add(
            Usuario(
                email=usuario["email"],
                nome=usuario["nome"],
                senha_hash=_hash(usuario["senha"]),
                admin=eh_admin,
                area_links=links,
            )
        )


def _seed_centros_custo(db: Session) -> None:
    """Carga inicial dos centros de custo a partir do CSV (Codigo;Nome)."""
    if db.scalar(select(CentroCusto.id).limit(1)) is not None:
        return
    if not _CSV_CENTROS_CUSTO.exists():
        return
    with _CSV_CENTROS_CUSTO.open(encoding="utf-8-sig", newline="") as arquivo:
        leitor = csv.DictReader(arquivo, delimiter=";")
        vistos: set[str] = set()
        for linha in leitor:
            codigo = (linha.get("Codigo") or "").strip()
            nome = (linha.get("Nome") or "").strip()
            if not codigo or codigo in vistos:
                continue
            vistos.add(codigo)
            db.add(CentroCusto(codigo=codigo, nome=nome))


def _seed_empresas_fornecedores(db: Session) -> None:
    """Carga inicial de empresas e fornecedores (dos literais que estavam em código)."""
    if db.scalar(select(Empresa.id).limit(1)) is None:
        for nome, rest, cnpj, rotina, produto, filial in EMPRESAS_SEED:
            db.add(Empresa(
                nome=nome, rest=rest, cnpj=cnpj, rotina_erp=rotina,
                prenota_produto=produto, prenota_filial=filial,
            ))
    # Fornecedor é semeado LINHA A LINHA (não "só se a tabela estiver vazia"):
    # um fornecedor novo, como a Claro, entra num banco que já tinha os antigos.
    # Sem isso, o primeiro lançamento falha com "CNPJ do fornecedor não cadastrado".
    for nome, cnpj in FORNECEDORES_SEED:
        if db.scalar(select(Fornecedor.id).where(Fornecedor.nome == nome)) is None:
            db.add(Fornecedor(nome=nome, cnpj=cnpj))


def _seed_colaboradores_demo(db: Session) -> None:
    """Cadastro fictício usado no lugar do Protheus (ver ColaboradorDemo)."""
    if db.scalar(select(ColaboradorDemo.id).limit(1)) is not None:
        return
    for cpf, nome, salario, matricula, filial, empresa, situacao in COLABORADORES_DEMO_SEED:
        db.add(ColaboradorDemo(
            cpf=cpf, nome=nome, salario=Decimal(salario), matricula=matricula,
            filial=filial, empresa=empresa, situacao=situacao,
        ))


def seed_inicial(db: Session) -> None:
    """Popula o banco com os dados iniciais (idempotente)."""
    _seed_parametros(db)
    _seed_consenso(db)
    _seed_usuarios_areas(db)
    _seed_centros_custo(db)
    _seed_empresas_fornecedores(db)
    _seed_colaboradores_demo(db)
    db.commit()
