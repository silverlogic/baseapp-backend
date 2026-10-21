from pathlib import Path

import pytest

from baseapp_core.tests.fixtures import *  # noqa: F401,F403

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
