#!/usr/bin/env bash
# Comprueba la convención de nombre de rama y de título de PR (ver CONTRIBUTING.md).
#
# Uso: bash .github/scripts/check-naming.sh "<rama>" "<título del PR>"
#
# Lo llama .github/workflows/pr-hygiene.yml, y sirve igual en local antes de abrir el PR:
#   bash .github/scripts/check-naming.sh "$(git branch --show-current)" "P5-01: repo base"
set -u

# Sin esto, en algunas configuraciones regionales [a-z] también acepta mayúsculas.
export LC_ALL=C

BRANCH="${1:-}"
TITLE="${2:-}"

TYPES='feat|fix|test|chore|docs|refactor|ci|build|perf|style'
# Ticket en ramas (minúsculas) y en títulos.
# Proyecto 6 (individual): p6-NN / P6-NN, con NN = número del issue de GitHub.
# Proyecto 5 (heredado): grupo A p5-NN / P5-NN, grupo B p5-tNN / TNN.
TICKET='t?[0-9]+'
TITLE_TICKET='(P[56]-[0-9]+|T[0-9]+)'
# p6-2-repo-p6 · p6-11-12-zonas · p5-01-repo-base · p5-t01-plazos · fix/nombre-corto
BRANCH_RE="^(p6-[0-9]+(-[0-9]+)*-[a-z0-9]+(-[a-z0-9]+)*|p5-$TICKET(-$TICKET)*-[a-z0-9]+(-[a-z0-9]+)*|($TYPES)/[a-z0-9]+(-[a-z0-9]+)*)\$"
# P6-2: texto · P6-11 P6-12: texto · P5-01: texto · T01: texto · P5-13/15: texto
# fix: texto · feat(ui): texto
TITLE_RE="^($TITLE_TICKET(/[0-9]+| $TITLE_TICKET)*|($TYPES)(\\([a-z0-9-]+\\))?): .+"

status=0

if ! [[ "$BRANCH" =~ $BRANCH_RE ]]; then
  echo "::error title=Nombre de rama::'$BRANCH' no sigue la convención. Usa p6-NN-descripcion" \
    "(Proyecto 6, NN = issue), p5-NN-/p5-tNN-descripcion (Proyecto 5) o tipo/descripcion con tipo en ($TYPES)," \
    "todo en minúsculas y con guiones. Ver CONTRIBUTING.md." >&2
  status=1
fi

if ! [[ "$TITLE" =~ $TITLE_RE ]]; then
  echo "::error title=Título del PR::'$TITLE' no sigue la convención. Usa 'P6-NN: descripción'" \
    "(Proyecto 6), 'P5-NN:'/'TNN:' (Proyecto 5), varios tickets como 'P6-NN P6-MM: ...' o" \
    "'tipo: descripción' con tipo en ($TYPES). Ver CONTRIBUTING.md." >&2
  status=1
fi

if [[ "$status" -eq 0 ]]; then
  echo "La rama y el título cumplen la convención."
fi
exit "$status"
