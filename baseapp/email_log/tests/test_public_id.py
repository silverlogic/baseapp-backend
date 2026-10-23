import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

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


@pytest.mark.django_db(transaction=True)
def test_migration_backfills_rows_written_before_it() -> None:
    """
    Migrate the active model's app back to before its DocumentId migration, write a row
    there (no trigger registers it), and migrate forward: the backfill, which runs on
    historical models, gives the row its public id.
    """
    app_label = EmailLog._meta.app_label
    before = [(app_label, "0001_initial")]
    executor = MigrationExecutor(connection)
    latest = [node for node in executor.loader.graph.leaf_nodes() if node[0] == app_label]
    executor.migrate(before)
    try:
        OldEmailLog = executor.loader.project_state(before).apps.get_model(app_label, "EmailLog")
        row = OldEmailLog.objects.create(channel="sms", delivery_to="+1")
        assert not _document_ids().filter(object_id=row.pk).exists()

        executor = MigrationExecutor(connection)
        executor.migrate(latest)
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(latest)

    ContentType.objects.clear_cache()
    log = EmailLog.objects.get(pk=row.pk)
    assert EmailLog.get_by_public_id(_document_ids().get(object_id=row.pk).public_id) == log
