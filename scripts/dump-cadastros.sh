#!/usr/bin/env bash
# Dump das tabelas de CADASTRO, para levar a configuração deste ambiente a um
# host novo (ex.: a subida de produção).
#
# O que vai: empresas, fornecedores, centros de custo, colaboradores PJ, faixas
# e valores da coparticipação, parâmetros, linhas telefônicas, áreas, usuários e
# os destinatários das notificações.
#
# O que NÃO vai, de propósito: `execucao`, `documento`, `envio_erp`,
# `envio_tentativa` e `processo_status`. As execuções deste ambiente são
# lançamentos feitos na base de TESTE do ERP; levá-las contaminaria o histórico
# oficial com títulos que não existem na base de produção. `processo_status`
# fica de fora porque a disponibilidade dos processos é decisão de cada host
# (em produção um processo pode nascer desativado).
#
# USUÁRIOS ficam FORA por padrão: o dump levaria os hashes de senha deste
# ambiente, inclusive os usuários de teste (admin/admin, rh/rh, operador/
# operador), reintroduzindo em produção credenciais de senha conhecida — o
# oposto do que a trava do seed garante. As ÁREAS e a matriz área × rateio vão,
# porque são a configuração de permissão; os usuários se criam no destino, cada
# host com suas próprias senhas.
#
# Uso:
#   ./scripts/dump-cadastros.sh                    # sem usuários (recomendado)
#   ./scripts/dump-cadastros.sh --com-usuarios     # inclui usuario e usuario_area
#   ./scripts/dump-cadastros.sh /tmp/saida.sql     # caminho explícito
#
# Restauração no host de destino (com a stack no ar e o banco JÁ migrado pela
# primeira subida da aplicação, que cria o schema):
#   docker compose exec -T postgres psql -U rateio -d rateio < cadastros-<data>.sql
#
# O dump usa --data-only com --on-conflict-do-nothing: ele NÃO recria tabelas e
# não sobrescreve o que já existe (o seed do host novo já cria empresas,
# fornecedores e faixas). Para substituir de verdade, limpe as tabelas antes.

set -euo pipefail
cd "$(dirname "$0")/.."

TABELAS=(
  # Organização e acesso (usuários só com --com-usuarios; ver acima)
  area area_rateio
  # Fiscal / cadastros
  empresa fornecedor centro_custo colaborador_pj
  # Coparticipação
  faixa_coparticipacao valor_coparticipacao parametro_rateio
  # Telefonia
  linha_telefonica
  # Notificações
  config_notificacao
)

COM_USUARIOS=0
ARGS=()
for arg in "$@"; do
  if [ "$arg" = "--com-usuarios" ]; then
    COM_USUARIOS=1
  else
    ARGS+=("$arg")
  fi
done
if [ "$COM_USUARIOS" -eq 1 ]; then
  TABELAS+=(usuario usuario_area)
fi

DESTINO="${ARGS[0]:-backups/cadastros-$(date +%Y%m%d-%H%M%S).sql}"
mkdir -p "$(dirname "$DESTINO")"

ARGS_TABELAS=()
for t in "${TABELAS[@]}"; do
  ARGS_TABELAS+=(--table="public.$t")
done

USUARIO="${POSTGRES_USER:-rateio}"
BANCO="${POSTGRES_DB:-rateio}"

docker compose exec -T postgres pg_dump \
  -U "$USUARIO" -d "$BANCO" \
  --data-only --column-inserts --on-conflict-do-nothing \
  "${ARGS_TABELAS[@]}" > "$DESTINO"

LINHAS=$(grep -c "^INSERT INTO" "$DESTINO" || true)
echo "Dump gerado: $DESTINO"
echo "Tabelas: ${#TABELAS[@]} | INSERTs: $LINHAS"
if [ "$COM_USUARIOS" -eq 1 ]; then
  echo "INCLUI usuários (hashes de senha). Confira se algum é usuário de teste."
else
  echo "SEM usuários: crie-os no destino (o admin inicial vem de SEED_ADMIN_*)."
fi
echo
echo "ATENÇÃO: o arquivo contém os hashes de senha dos usuários e os e-mails"
echo "cadastrados. Trate como dado sensível (não versione, transfira por canal"
echo "seguro e remova do host de destino depois de restaurar)."
