#!/usr/bin/env bash
# CI gate: package catalogs must be fresh (makemessages produces no diff beyond
# the POT-Creation-Date header) and complete (0 untranslated, 0 fuzzy).
#
#   docker compose run --rm web uv run bash scripts/i18n/check_translations.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
source scripts/i18n/packages.sh

locale_dirs=()
for package in "${I18N_PACKAGES[@]}"; do
  [ -d "$package/locale" ] && locale_dirs+=("$package/locale")
done

# Snapshot the catalogs, regenerate, and compare (ignoring the POT-Creation-Date line).
snapshot="$(mktemp -d)"
trap 'rm -rf "$snapshot"' EXIT
for dir in "${locale_dirs[@]}"; do
  mkdir -p "$snapshot/$dir"
  cp -R "$dir/." "$snapshot/$dir/"
done

bash scripts/i18n/makemessages.sh --verbosity 0

# Compare wrap-normalized content (editors wrap differently from msgmerge) minus the date.
normalized() {
  find "$1" -name '*.po' | sort | while IFS= read -r po; do
    echo "== ${po#"$1"/}"
    msgcat --no-wrap "$po" | grep -v '^"POT-Creation-Date'
  done
}

stale=0
for dir in "${locale_dirs[@]}"; do
  if ! diff -u <(normalized "$snapshot/$dir") <(normalized "$dir") >/tmp/catalog.diff; then
    stale=1
    cat /tmp/catalog.diff >&2
  fi
done
if [ "$stale" -ne 0 ]; then
  echo "Catalogs are stale: scripts/i18n/makemessages.sh changed them. Regenerate, translate, commit." >&2
  exit 1
fi

locale_dir_args=()
for dir in "${locale_dirs[@]}"; do
  locale_dir_args+=(--locale-dir "$dir")
done
django-admin check_translations --no-makemessages "${locale_dir_args[@]}"
