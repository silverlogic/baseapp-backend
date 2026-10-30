from pathlib import Path

import pytest
from celery import current_app

from baseapp_core.tests.fixtures import *  # noqa: F401,F403

# Apply Django's CELERY_* settings (CELERY_TASK_ALWAYS_EAGER=True) to the current Celery app,
# as baseapp_comments does, so CeleryEmailBackend's tasks run in-process. Module level, so
# threads (the idempotency race test) see it too.
current_app.config_from_object("django.conf:settings", namespace="CELERY")

LOCMEM_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture(autouse=True)
def email_log_backend(settings) -> None:
    """Send through the logging backend, delivering into ``mail.outbox``."""
    settings.EMAIL_BACKEND = "baseapp.email_log.backends.EmailBackend"
    settings.DJMAIL_REAL_BACKEND = LOCMEM_BACKEND
    settings.DJMAIL_MAX_RETRY_NUMBER = 3


@pytest.fixture
def failing_transport(settings) -> None:
    settings.DJMAIL_REAL_BACKEND = "baseapp.email_log.tests.helpers.FailingBackend"


@pytest.fixture
def unreachable_transport(settings) -> None:
    settings.DJMAIL_REAL_BACKEND = "baseapp.email_log.tests.helpers.UnreachableBackend"


@pytest.fixture
def attachment_storage(settings, tmp_path: Path) -> Path:
    settings.STORAGES = {
        **settings.STORAGES,
        "email_attachments": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path)},
        },
    }
    settings.BASEAPP_EMAIL_LOG_ATTACHMENT_STORAGE = "email_attachments"
    settings.BASEAPP_EMAIL_LOG_STORE_ATTACHMENTS = True
    return tmp_path
