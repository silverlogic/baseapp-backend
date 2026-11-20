import pytest
from django.core import mail
from djmail.models import Message

from baseapp.email_log.models import get_email_log_model
from baseapp.email_log.services import get_email_log
from baseapp.email_log.tasks import retry_failed_emails

from .helpers import TRANSPORT_ERROR, make_email

EmailLog = get_email_log_model()

pytestmark = pytest.mark.django_db


def test_transport_error_is_visible_as_failed(failing_transport) -> None:
    email = make_email()
    sent = email.send()

    # djmail swallows the exception: the caller only sees nothing was sent...
    assert sent == 0
    log = get_email_log(email)
    log.refresh_from_db()
    # ...and the log says why.
    assert log.status == "failed"
    assert "SMTPException" in log.error
    assert TRANSPORT_ERROR in log.error
    assert log.message.retry_count == 0
    assert EmailLog.objects.with_status("failed").get() == log


def test_transport_reporting_nothing_sent_is_failed(settings) -> None:
    settings.DJMAIL_REAL_BACKEND = "baseapp.email_log.tests.helpers.NothingSentBackend"
    email = make_email()
    email.send()

    log = get_email_log(email)
    log.refresh_from_db()
    assert log.status == "failed"
    assert log.message.retry_count == 0


def test_retry_resends_failed_messages(failing_transport, settings) -> None:
    email = make_email()
    email.send()
    log = get_email_log(email)

    settings.DJMAIL_REAL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    assert retry_failed_emails() == 1

    log.refresh_from_db()
    assert log.status == "sent"
    assert log.error == ""
    assert log.sent_at is not None
    assert len(mail.outbox) == 1


def test_retry_counts_attempts_and_discards_after_the_limit(failing_transport, settings) -> None:
    settings.DJMAIL_MAX_RETRY_NUMBER = 2
    email = make_email()
    email.send()
    message = get_email_log(email).message

    # Retried while retry_count <= 2: attempts 0 (the send), 1, 2, 3.
    for expected in (1, 2, 3):
        retry_failed_emails()
        message.refresh_from_db()
        assert message.status == Message.STATUS_FAILED
        assert message.retry_count == expected

    retry_failed_emails()
    message.refresh_from_db()
    assert message.status == Message.STATUS_DISCARDED
    assert get_email_log(email).status == "discarded"


def test_retry_sends_pending_low_priority_messages() -> None:
    email = make_email()
    email.priority = Message.PRIORITY_LOW
    email.send()
    assert mail.outbox == []

    assert retry_failed_emails() == 1
    assert len(mail.outbox) == 1
    log = get_email_log(email)
    log.refresh_from_db()
    assert log.status == "sent"


def test_retry_also_covers_messages_sent_without_the_log() -> None:
    from djmail.backends.default import EmailBackend as DjmailBackend

    message_count = DjmailBackend().send_messages([make_email()])
    assert message_count == 1
    Message.objects.update(status=Message.STATUS_FAILED, retry_count=0)

    assert retry_failed_emails() == 1
    assert Message.objects.get().status == Message.STATUS_SENT
