from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from djmail.models import Message
from freezegun import freeze_time

from baseapp.email_log.attachments import read_stored_attachment
from baseapp.email_log.models import get_email_log_model
from baseapp.email_log.services import log_channel_message, send_logged
from baseapp.email_log.tasks import purge_email_logs

from .helpers import make_email

EmailLog = get_email_log_model()

pytestmark = pytest.mark.django_db


def _send_days_ago(days: int, **kwargs: Any) -> "EmailLog":
    with freeze_time(timezone.now() - timedelta(days=days)):
        return send_logged(make_email(), **kwargs)


def test_default_retention_keeps_everything() -> None:
    _send_days_ago(1000, idempotency_key=None)

    assert purge_email_logs() == 0
    assert EmailLog.objects.count() == 1
    assert Message.objects.count() == 1


def test_purges_old_rows_with_their_messages(settings) -> None:
    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS = 30
    old = _send_days_ago(31, idempotency_key=None)
    recent = _send_days_ago(29, idempotency_key=None)
    with freeze_time(timezone.now() - timedelta(days=40)):
        old_sms = log_channel_message(channel="sms", to="+1", body_text="x")

    assert purge_email_logs() == 2

    assert list(EmailLog.objects.all()) == [recent]
    assert not Message.objects.filter(pk=old.message_id).exists()
    assert Message.objects.filter(pk=recent.message_id).exists()
    assert not EmailLog.objects.filter(pk=old_sms.pk).exists()


def test_argument_overrides_the_setting(settings) -> None:
    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS = 365
    _send_days_ago(10, idempotency_key=None)

    assert purge_email_logs(older_than_days=7) == 1
    assert not EmailLog.objects.exists()


def test_rows_with_an_idempotency_key_are_kept(settings) -> None:
    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS = 30
    keyed = _send_days_ago(60, idempotency_key="order-1")

    assert purge_email_logs() == 0
    assert list(EmailLog.objects.all()) == [keyed]
    assert Message.objects.filter(pk=keyed.message_id).exists()

    settings.BASEAPP_EMAIL_LOG_PURGE_IDEMPOTENT = True
    assert purge_email_logs() == 1
    assert not EmailLog.objects.exists()
    assert not Message.objects.exists()


def test_purges_old_unlogged_djmail_messages(settings) -> None:
    from djmail.backends.default import EmailBackend as DjmailBackend

    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS = 30
    with freeze_time(timezone.now() - timedelta(days=31)):
        DjmailBackend().send_messages([make_email()])
    assert Message.objects.filter(email_log__isnull=True).count() == 1

    purge_email_logs()
    assert not Message.objects.exists()


def test_purge_deletes_stored_attachments(settings, attachment_storage) -> None:
    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS = 30
    email = make_email()
    email.attach("invoice.pdf", b"%PDF", "application/pdf")
    with freeze_time(timezone.now() - timedelta(days=31)):
        log = send_logged(email, idempotency_key=None)
    entry = log.attachments[0]
    assert read_stored_attachment(entry) == b"%PDF"

    purge_email_logs()

    assert not (attachment_storage / entry["path"]).exists()


def test_resends_survive_their_purged_original(settings) -> None:
    from baseapp.email_log.services import resend

    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS = 30
    original = _send_days_ago(31, idempotency_key=None)
    copy = resend(original)

    purge_email_logs()

    copy.refresh_from_db()
    assert copy.resend_of is None
    assert copy.status == "sent"
