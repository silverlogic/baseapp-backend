from datetime import timedelta
from pathlib import Path
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

NOTHING = {"deleted": 0, "scrubbed": 0, "unlogged_messages": 0}


def _counts(**kwargs: int) -> dict[str, int]:
    return {**NOTHING, **kwargs}


def _send_days_ago(days: int, **kwargs: Any) -> "EmailLog":
    with freeze_time(timezone.now() - timedelta(days=days)):
        return send_logged(make_email(), **kwargs)


def _send_with_attachment_days_ago(days: int, **kwargs: Any) -> "EmailLog":
    email = make_email()
    email.attach("invoice.pdf", b"%PDF", "application/pdf")
    with freeze_time(timezone.now() - timedelta(days=days)):
        return send_logged(email, **kwargs)


def test_default_retention_keeps_everything() -> None:
    _send_days_ago(1000, idempotency_key=None)
    _send_days_ago(1000, idempotency_key="order-1", context={"token": "secret"})

    assert purge_email_logs() == NOTHING
    assert EmailLog.objects.count() == 2
    assert Message.objects.count() == 2
    assert EmailLog.objects.get(idempotency_key="order-1").context == {"token": "secret"}


def test_purges_old_rows_with_their_messages(settings) -> None:
    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS = 30
    old = _send_days_ago(31, idempotency_key=None)
    recent = _send_days_ago(29, idempotency_key=None)
    with freeze_time(timezone.now() - timedelta(days=40)):
        old_sms = log_channel_message(channel="sms", to="+1", body_text="x")

    assert purge_email_logs() == _counts(deleted=2)

    assert list(EmailLog.objects.all()) == [recent]
    assert not Message.objects.filter(pk=old.message_id).exists()
    assert Message.objects.filter(pk=recent.message_id).exists()
    assert not EmailLog.objects.filter(pk=old_sms.pk).exists()


def test_argument_overrides_the_setting(settings) -> None:
    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS = 365
    _send_days_ago(10, idempotency_key=None)

    assert purge_email_logs(older_than_days=7) == _counts(deleted=1)
    assert not EmailLog.objects.exists()


def test_rows_with_an_idempotency_key_are_scrubbed_not_deleted(
    settings, attachment_storage: Path
) -> None:
    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS = 30
    keyed = _send_with_attachment_days_ago(
        60,
        idempotency_key="order-1",
        template="orders/confirmed",
        context={"accept_url": "https://example.com/accept/secret-token"},
        category="orders",
    )
    path = keyed.attachments[0]["path"]
    assert (attachment_storage / path).exists()

    assert purge_email_logs() == _counts(scrubbed=1)

    keyed.refresh_from_db()
    assert list(EmailLog.objects.all()) == [keyed]
    assert keyed.idempotency_key == "order-1"
    assert keyed.message_id is None
    assert not Message.objects.exists()
    assert keyed.context == {}
    assert keyed.attachments == [
        {"name": "invoice.pdf", "content_type": "application/pdf", "size": 4}
    ]
    assert not (attachment_storage / path).exists()
    # Who, what and when remain, the djmail message's subject, sender, status and sent
    # date included.
    assert keyed.recipients == ["to@example.com"]
    assert keyed.template == "orders/confirmed"
    assert keyed.category == "orders"
    assert keyed.subject == "Your invoice"
    assert keyed.from_email == "from@example.com"
    assert keyed.status == EmailLog.Status.SENT
    assert keyed.sent_at is not None
    assert keyed.scrubbed_at is not None
    assert list(EmailLog.objects.with_status(EmailLog.Status.SENT)) == [keyed]
    # The key keeps blocking a second send.
    assert send_logged(make_email(), idempotency_key="order-1") == keyed
    assert Message.objects.count() == 0

    # Already scrubbed: nothing left to do on the next run.
    assert purge_email_logs() == NOTHING


def test_scrubs_the_text_of_keyed_rows_of_other_channels(settings) -> None:
    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS = 30
    with freeze_time(timezone.now() - timedelta(days=31)):
        sms = log_channel_message(
            channel="sms", to="+1", body_text="Your code is 123456", idempotency_key="code-1"
        )

    assert purge_email_logs() == _counts(scrubbed=1)

    sms.refresh_from_db()
    assert sms.delivery_body_text == ""
    assert sms.delivery_to == "+1"
    assert sms.scrubbed_at is not None


def test_purge_idempotent_deletes_keyed_rows(settings) -> None:
    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS = 30
    settings.BASEAPP_EMAIL_LOG_PURGE_IDEMPOTENT = True
    _send_days_ago(60, idempotency_key="order-1")

    assert purge_email_logs() == _counts(deleted=1)
    assert not EmailLog.objects.exists()
    assert not Message.objects.exists()


def test_retention_by_category_on_top_of_the_general_one(settings) -> None:
    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS = 90
    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS_BY_CATEGORY = {"auth": 14, "reports": 365}
    reset = _send_days_ago(15, idempotency_key=None, category="auth")
    fresh_reset = _send_days_ago(13, idempotency_key=None, category="auth")
    invoice = _send_days_ago(15, idempotency_key=None, category="billing")
    old_report = _send_days_ago(100, idempotency_key=None, category="reports")
    keyed_code = _send_days_ago(15, idempotency_key="code-1", category="auth")

    # A category can only shorten the retention: the 100-day-old report goes at 90 days.
    assert purge_email_logs() == _counts(deleted=2, scrubbed=1)

    remaining = set(EmailLog.objects.values_list("pk", flat=True))
    assert remaining == {fresh_reset.pk, invoice.pk, keyed_code.pk}
    assert reset.pk not in remaining and old_report.pk not in remaining
    keyed_code.refresh_from_db()
    assert keyed_code.message_id is None


def test_retention_by_category_without_a_general_retention(settings) -> None:
    from djmail.backends.default import EmailBackend as DjmailBackend

    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS_BY_CATEGORY = {"auth": 14}
    _send_days_ago(15, idempotency_key=None, category="auth")
    kept = _send_days_ago(1000, idempotency_key=None, category="billing")
    with freeze_time(timezone.now() - timedelta(days=1000)):
        DjmailBackend().send_messages([make_email()])

    # Unlogged djmail messages have no category: only the general retention purges them.
    assert purge_email_logs() == _counts(deleted=1)
    assert list(EmailLog.objects.all()) == [kept]
    assert Message.objects.filter(email_log__isnull=True).count() == 1


def test_dry_run_counts_and_changes_nothing(settings, attachment_storage: Path) -> None:
    from djmail.backends.default import EmailBackend as DjmailBackend

    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS = 30
    old = _send_with_attachment_days_ago(31, idempotency_key=None)
    keyed = _send_days_ago(31, idempotency_key="order-1", context={"a": 1})
    _send_days_ago(1, idempotency_key=None)
    with freeze_time(timezone.now() - timedelta(days=31)):
        DjmailBackend().send_messages([make_email()])

    assert purge_email_logs(dry_run=True) == {
        "deleted": 1,
        "scrubbed": 1,
        "unlogged_messages": 1,
    }

    assert EmailLog.objects.count() == 3
    assert Message.objects.count() == 4
    assert (attachment_storage / old.attachments[0]["path"]).exists()
    keyed.refresh_from_db()
    assert keyed.context == {"a": 1}
    assert keyed.message_id is not None


def test_purges_old_unlogged_djmail_messages(settings) -> None:
    from djmail.backends.default import EmailBackend as DjmailBackend

    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS = 30
    with freeze_time(timezone.now() - timedelta(days=31)):
        DjmailBackend().send_messages([make_email()])
    assert Message.objects.filter(email_log__isnull=True).count() == 1

    assert purge_email_logs() == _counts(unlogged_messages=1)
    assert not Message.objects.exists()


def test_purge_deletes_stored_attachments(settings, attachment_storage: Path) -> None:
    settings.BASEAPP_EMAIL_LOG_RETENTION_DAYS = 30
    log = _send_with_attachment_days_ago(31, idempotency_key=None)
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
