#!/usr/bin/env bash

PACKAGES=(
  # "auth"
  # # "baseapp-auth/baseapp_referrals"
  # "blocks"
  # "chats"
  # "comments"
  # "core"
  # # "drf-view-action-permissions
  # "e2e"
  # "follows"
  # # "message-templates"
  # "notifications"
  # "organizations"
  # "pages"
  # "payments"
  # "profiles"
  # "ratings"
  "reactions"
  # "reports"
  # # "social-auth"
  # # "url-shortening"
  # "wagtail"
)

FILES_TO_MOVE=(
  "setup_test_migrations.sh"
  "MANIFEST.in"
)

mkdir -p baseapp/pending_test_projects

echo "Moving files to new structure"
for pkg in "${PACKAGES[@]}"; do
  echo "Moving package: $pkg"

  git mv "baseapp-$pkg/baseapp_$pkg" "baseapp/baseapp/$pkg"
  git mv baseapp-$pkg/*.md baseapp/baseapp/$pkg/
  git mv baseapp-$pkg/testproject baseapp/pending_test_projects/$pkg

  for file_to_move in "${FILES_TO_MOVE[@]}"; do
  if [[ -f "baseapp-$pkg/$file_to_move" ]]; then
    git mv baseapp-$pkg/$file_to_move baseapp/baseapp/$pkg/
  fi
  done

  git commit -am "$pkg: move from baseapp-$pkg to baseapp/baseapp"
done
echo "  -> Done."

echo "Removing unecessary files"
for pkg in "${PACKAGES[@]}"; do
  rm -rf baseapp-$pkg
done
  git commit -am "remove unecessary files from old baseapp structure"
echo "  -> Done."

echo "Fixing apps.py files to make it backwards compatible"
for pkg in "${PACKAGES[@]}"; do
  # Path to apps.py -- adjust if your structure differs
  APPS_PY="baseapp/baseapp/${pkg}/apps.py"
  if [[ -f "$APPS_PY" ]]; then
        # 1) Replace: class SomeNameConfig(AppConfig) -> class PackageConfig(AppConfig)
    sed -i '' 's/class .*Config(AppConfig):/class PackageConfig(AppConfig):/' "$APPS_PY"

    # 2) Replace: name = "baseapp_xyz" -> name = "baseapp.xyz"
    #    And add:   label = "baseapp_xyz"
    sed -i '' -E \
      's/name = "baseapp_([^"]*)"/name = "baseapp.\1"\n    label = "baseapp_\1"/' "$APPS_PY"
  else
    echo "  -> Creating file not found: $APPS_PY"
    # Capitalize the first letter of the package name
    capitalized_pkg="$(echo "${pkg:0:1}" | tr '[:lower:]' '[:upper:]')${pkg:1}"
    
    cat <<EOF > "$APPS_PY"
from django.apps import AppConfig


class PackageConfig(AppConfig):
    name = "baseapp.${pkg}"
    label = "baseapp_${pkg}"
    verbose_name = "BaseApp ${capitalized_pkg}"
    default_auto_field = "django.db.models.BigAutoField"
EOF
    git add $APPS_PY
  fi
done
git commit -am "Update apps.py for backwards compatibility"
echo "  -> Done."

echo "Fixing imports in python files"
for pkg in "${PACKAGES[@]}"; do
  find ./ -type f -name "*.py" | while read -r file; do    
    sed -i '' "s/from baseapp_$pkg/from baseapp.$pkg/g" "$file"
    sed -i '' "s/import baseapp_$pkg/import baseapp.$pkg/g" "$file"
    sed -i '' "s/baseapp_$pkg.permissions/baseapp.$pkg.permissions/g" "$file"
    sed -i '' "s/baseapp_$pkg.notifications/baseapp.$pkg.notifications/g" "$file"
    sed -i '' "s/baseapp_$pkg.models/baseapp.$pkg.models/g" "$file"
    sed -i '' "s/baseapp_$pkg.graphql/baseapp.$pkg.graphql/g" "$file"
  done

  git commit -am "$pkg: fix imports"
done
echo "  -> Done."

echo "Looking for references to old package names"
for pkg in "${PACKAGES[@]}"; do
  MATCHES=$(
    grep -rn "baseapp_$pkg" . \
    | grep -v "swapper\.load_model" \
    | grep -v "has_perm" \
    | grep -v "/migrations/" \
    | grep -v "apps.py" \
    | grep -v "if perm" \
    | grep -v "activity_name" \
    | grep -v "swapper.swappable_setting"
  )

  while IFS=: read -r file lineNum text; do
    sed -i '' "${lineNum}s/baseapp_$pkg/baseapp.$pkg/g" "$file"
  done <<< "$MATCHES"
  
  git commit -am "[TO BE REVIEWED] $pkg: fix references to old package name [TO BE REVIEWED]"

  grep -r "baseapp_$pkg" .
done
echo "  -> Done."
