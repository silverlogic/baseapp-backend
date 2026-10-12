#!/usr/bin/env bash
# Compile every .po catalog in the repo into its .mo (not tracked in git).
#
#   docker compose run --rm web bash scripts/i18n/compilemessages.sh
#
# Uses msgfmt directly so it works before Django is installed (Docker builds,
# the PyPI publish job) as well as inside the dev container.
set -euo pipefail
cd "$(dirname "$0")/../.."

find . -path ./node_modules -prune -o -name '*.po' -print0 \
  | while IFS= read -r -d '' po; do
      msgfmt --check-format -o "${po%.po}.mo" "$po"
    done
echo "compiled $(find . -name '*.mo' | wc -l) catalog(s)"
