#!/bin/bash

# This script is to refresh the tests migrations after any model changes. We don't need to keep old
# versions of the migrations for tests, so we delete the initial migration and create a new one.

rm -f baseapp_wagtail/tests/migrations/0001_initial.py
echo "Deleted baseapp_wagtail/tests/migrations/0001_initial.py"

docker compose exec web bash -c "
  cd baseapp-wagtail &&
  export DJANGO_SETTINGS_MODULE=testproject.settings_for_tests &&
  echo 'DJANGO_SETTINGS_MODULE set to testproject.settings_for_tests' &&
  python manage.py makemigrations tests &&
  echo 'Migrations created for tests' &&
  export DJANGO_SETTINGS_MODULE=testproject.settings &&
  echo 'DJANGO_SETTINGS_MODULE set to testproject.settings'
"
echo "Migration setup for tests completed"
