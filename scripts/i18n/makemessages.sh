#!/usr/bin/env bash
# Regenerate every package's translation catalogs (es, pt).
#
#   docker compose run --rm web uv run bash scripts/i18n/makemessages.sh
#
# Runs Django's `makemessages` inside each package directory so strings land in
# that package's own `locale/`. `baseapp_core`'s `makemessages` override adds
# Jinja (.j2) extraction and the defaults from `BA_MAKEMESSAGES_DEFAULTS`.
set -euo pipefail
cd "$(dirname "$0")/../.."
source scripts/i18n/packages.sh

locale_args=()
for locale in "${I18N_LOCALES[@]}"; do
  locale_args+=(-l "$locale")
done

for package in "${I18N_PACKAGES[@]}"; do
  mkdir -p "$package/locale"
  echo "== $package"
  (cd "$package" && django-admin makemessages "${locale_args[@]}" "$@")
  # makemessages leaves an empty locale/ behind when a package has no strings.
  rmdir "$package/locale" 2>/dev/null || true
done
