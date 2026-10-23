import importlib

import pytest
from django.apps import apps
from django.contrib.contenttypes.models import ContentType

from baseapp.email_log.models import get_email_log_model
from baseapp.email_log.services import log_channel_message, send_logged
from baseapp_core.models import DocumentId

from .helpers import make_email

EmailLog = get_email_log_model()

pytestmark = pytest.mark.django_db


def _document_ids() -> "DocumentId.objects":
    return DocumentId.objects.filter(content_type=ContentType.objects.get_for_model(EmailLog))


def test_rows_get_a_public_id() -> None:
    log = send_logged(make_email(), idempotency_key=None)
    sms = log_channel_message(channel="sms", to="+1", body_text="x")

    assert log.public_id is not None
    assert log.public_id != sms.public_id
    assert EmailLog.get_by_public_id(log.public_id) == log
    assert _document_ids().count() == 2


def test_deleting_a_row_drops_its_public_id() -> None:
    log = send_logged(make_email(), idempotency_key=None)
    log.delete()

    assert not _document_ids().exists()


def test_migration_backfills_rows_written_before_it() -> None:
    log = send_logged(make_email(), idempotency_key=None)
    _document_ids().delete()

    migration = importlib.import_module(
        f"{EmailLog.__module__.rsplit('.', 1)[0]}.migrations.0002_emaillog_document_id"
    )
    migration.backfill_document_ids(apps, None)

    assert EmailLog.get_by_public_id(_document_ids().get().public_id) == log
