# syntax=docker/dockerfile:1.7
#
# Backend do FinanceFlow (FastAPI): multi-stage, venv copiado, usuário
# não-root, tini como PID 1 e uvicorn com cabeçalhos de proxy.
#
# O hot reload NÃO está aqui: ele vive no docker-compose.override.yml de
# desenvolvimento. Imagem que embarca `--reload` leva o servidor de
# desenvolvimento para produção.

# ---- build: resolve as dependências num venv próprio ----
FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# build-essential só existe NESTE estágio (pacotes sem wheel pronto). A imagem
# final não carrega compilador.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
# Versões fixas no requirements (equivalente ao `npm ci`): sem fallback, para
# não reintroduzir build não reproduzível.
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install -r requirements.txt

# ---- runtime: só o venv + o código, sem toolchain, sem root ----
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app

# tini como PID 1: encaminha SIGTERM ao uvicorn (e ao processo filho do
# --reload em dev). Sem ele, `docker stop` espera o timeout e mata à força.
# A imagem `python:slim` não traz usuário não-root pronto, ao contrário da
# `node:*`, por isso o useradd é obrigatório.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 1000 --create-home --shell /usr/sbin/nologin app

COPY --from=build --chown=app:app /opt/venv /opt/venv
COPY --chown=app:app . .

USER app
EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
# `--proxy-headers` + `--forwarded-allow-ips`: atrás do nginx e do Traefik, é o
# que faz o IP e o esquema do cliente chegarem corretos (equivalente do
# `trust proxy` do Express). Sem isso, a auditoria registra o IP do proxy.
#
# Migrações: este projeto aplica o schema no `lifespan` (create_all + migrações
# idempotentes + seed), não com Alembic. A condição dessa escolha é RÉPLICA
# ÚNICA — duas réplicas subindo juntas migrariam em paralelo.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
