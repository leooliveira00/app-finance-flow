#!/usr/bin/env bash
#
# Escreve a versão do release em backend/app/version.py.
#
# Chamado pelo `prepareCmd` do @semantic-release/exec (ver .releaserc.json), que
# passa ${nextRelease.version} como único argumento. Existe como script — e não
# como um `printf` inline no .releaserc.json — porque o arquivo gerado precisa
# manter o comentário explicativo, e escapar isso dentro do JSON seria ilegível.
#
# O backend é Python: não há `npm version` para bumpar. A versão vive em dois
# lugares, os dois reescritos pelo release: o `[project].version` do
# pyproject.toml (metadado do pacote) e este módulo, que é a fonte consultada em
# RUNTIME (FastAPI(version=...) e GET /api/health).
set -euo pipefail

versao="${1:?uso: escreve-versao-backend.sh <versao>}"
destino="$(dirname "$0")/../backend/app/version.py"

cat > "$destino" <<PY
"""
Versão da aplicação (backend).

ARQUIVO GERADO — não editar à mão. É reescrito pelo semantic-release a cada
release (ver .releaserc.json e scripts/escreve-versao-backend.sh); qualquer
alteração manual é perdida no próximo \`npm run release\`.
"""

__version__ = "${versao}"
PY

echo "backend/app/version.py -> ${versao}"
