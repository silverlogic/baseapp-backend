#!/usr/bin/env bash
# Lists the package directories that ship translation catalogs (sourced by the
# other scripts in this directory). A package belongs here as soon as it has a
# `locale/` directory; `makemessages.sh` creates one for any package that has
# translatable strings.
set -euo pipefail

I18N_PACKAGES=(
  baseapp/activity_log
  baseapp/content_feed
  baseapp/files
  baseapp_api_key
  baseapp_auth
  baseapp_blocks
  baseapp_chats
  baseapp_comments
  baseapp_core
  baseapp_drf_view_action_permissions
  baseapp_follows
  baseapp_mentions
  baseapp_message_templates
  baseapp_notifications
  baseapp_organizations
  baseapp_pages
  baseapp_payments
  baseapp_pdf
  baseapp_profiles
  baseapp_ratings
  baseapp_reactions
  baseapp_referrals
  baseapp_reports
  baseapp_url_shortening
  baseapp_wagtail
)

I18N_LOCALES=(es pt_BR)

# `baseapp_core`'s makemessages override (Jinja extraction + BA_MAKEMESSAGES_DEFAULTS)
# is only found when Django settings import, and testproject.settings reads these at
# import time. No database connection is made.
export DJANGO_SETTINGS_MODULE=testproject.settings
export DB_NAME="${DB_NAME:-baseapp}" DB_USER="${DB_USER:-baseapp}" DB_PASS="${DB_PASS:-baseapp}"
export DB_SERVICE="${DB_SERVICE:-localhost}" DB_PORT="${DB_PORT:-5432}"
export STRIPE_SECRET_KEY="${STRIPE_SECRET_KEY:-N/A}" STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET:-N/A}"
