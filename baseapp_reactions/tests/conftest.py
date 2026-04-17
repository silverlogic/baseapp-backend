from celery import current_app

from baseapp_core.graphql.testing.fixtures import *  # noqa
from baseapp_core.tests.fixtures import *  # noqa

# Apply Django's CELERY_* settings (including CELERY_TASK_ALWAYS_EAGER=True) to the
# Celery default_app so .delay() runs synchronously in tests. Must run at module level
# — a fixture would only configure the app instance on the main thread's task stack,
# which worker threads (spawned by database_sync_to_async in async tests) can't see.
current_app.config_from_object("django.conf:settings", namespace="CELERY")
