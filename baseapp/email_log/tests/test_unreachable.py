"""
A transport that cannot be reached fails in ``connection.open()``, before any message is
handed to it. Every message must still end up ``failed`` with the error, and be retried.
"""

import threading
from datetime import timedelta

import pytest
from django.core import mail
from django.db import connection as db_connection
from django.db import transaction
from django.utils import timezone
from djmail.models import Message

from baseapp.email_log.backends import CeleryEmailBackend
from baseapp.email_log.models import get_email_log_model
from baseapp.email_log.services import get_email_log, send_logged
from baseapp.email_log.tasks import retry_failed_emails, send_queued_messages

from .conftest import LOCMEM_BACKEND
from .helpers import UNREACHABLE_ERROR, UnreachableBackend, make_email

EmailLog = get_email_log_model()

pytestmark = pytest.mark.django_db

SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"


def _fresh_log(email) -> "EmailLog":
    log = get_email_log(email)
    log.refresh_from_db()
    return log


def _assert_failed(email, *, error: str, retry_count: int = 0) -> None:
    log = _fresh_log(email)
    assert log.status == "failed"
    assert error in log.error
    assert log.message.retry_count == retry_count


def test_unreachable_smtp_server_is_failed_not_queued(settings) -> None:
    # Django's real SMTP backend, pointed at a closed port: open() raises.
    settings.DJMAIL_REAL_BACKEND = SMTP_BACKEND
    settings.EMAIL_HOST = "127.0.0.1"
    settings.EMAIL_PORT = 1
    settings.EMAIL_TIMEOUT = 5
    email = make_email()

    assert email.send() == 0

    _assert_failed(email, error="ConnectionRefusedError")

    # The transport comes back: the retry task sends it.
    settings.DJMAIL_REAL_BACKEND = LOCMEM_BACKEND
    assert retry_failed_emails() == 1
    assert _fresh_log(email).status == "sent"
    assert len(mail.outbox) == 1


def test_unreachable_transport_fails_every_message_and_holds_low_priority(
    unreachable_transport,
) -> None:
    first, second, low = make_email(), make_email(subject="Second"), make_email()
    low.priority = Message.PRIORITY_LOW

    # The held one counts as sent, as with djmail.
    assert mail.get_connection().send_messages([first, second, low]) == 1

    _assert_failed(first, error=UNREACHABLE_ERROR)
    _assert_failed(second, error=UNREACHABLE_ERROR)
    assert _fresh_log(low).message.status == Message.STATUS_PENDING


def test_send_logged_through_an_unreachable_connection_returns_the_failed_row() -> None:
    log = send_logged(make_email(), idempotency_key="k", connection=UnreachableBackend())

    log.refresh_from_db()
    assert log.status == "failed"
    assert UNREACHABLE_ERROR in log.error


def test_error_closing_the_connection_does_not_reach_the_caller(settings) -> None:
    settings.DJMAIL_REAL_BACKEND = "baseapp.email_log.tests.helpers.ClosingFailsBackend"
    email = make_email()

    assert email.send() == 1
    assert _fresh_log(email).status == "sent"


def test_celery_worker_with_unreachable_transport(
    settings, unreachable_transport, django_capture_on_commit_callbacks
) -> None:
    settings.EMAIL_BACKEND = "baseapp.email_log.backends.CeleryEmailBackend"
    email = make_email()

    with django_capture_on_commit_callbacks(execute=True):
        assert email.send() == 1

    _assert_failed(email, error=UNREACHABLE_ERROR)


def test_broker_down_marks_the_queued_messages_failed(
    monkeypatch, django_capture_on_commit_callbacks
) -> None:
    def broker_down(*args, **kwargs):
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(send_queued_messages, "delay", broker_down)
    email = make_email()

    # The error does not reach the caller after its transaction committed.
    with django_capture_on_commit_callbacks(execute=True):
        assert CeleryEmailBackend().send_messages([email]) == 1

    _assert_failed(email, error="broker unreachable")
    assert mail.outbox == []

    assert retry_failed_emails() == 1
    assert _fresh_log(email).status == "sent"


def test_retry_with_unreachable_transport_counts_one_attempt_and_still_discards(
    settings, failing_transport
) -> None:
    settings.DJMAIL_MAX_RETRY_NUMBER = 1
    over_limit = make_email(subject="Over the limit")
    over_limit.send()
    Message.objects.filter(uuid=_fresh_log(over_limit).message_id).update(retry_count=2)
    retried = make_email(subject="Retried")
    retried.send()
    pending = make_email(subject="Pending")
    pending.priority = Message.PRIORITY_LOW
    pending.send()

    settings.DJMAIL_REAL_BACKEND = "baseapp.email_log.tests.helpers.UnreachableBackend"
    assert retry_failed_emails() == 0

    # The discard step ran although the transport was down...
    assert _fresh_log(over_limit).status == "discarded"
    # ...and each message was attempted once: a pending message that fails now is retried
    # by the next run, not again in this one.
    _assert_failed(retried, error=UNREACHABLE_ERROR, retry_count=1)
    _assert_failed(pending, error=UNREACHABLE_ERROR, retry_count=0)


def _queued_draft(django_capture_on_commit_callbacks, *, minutes_ago: int) -> "EmailLog":
    """A logged message the Celery backend wrote but whose task never ran."""
    email = make_email()
    with django_capture_on_commit_callbacks(execute=False):
        CeleryEmailBackend().send_messages([email])
    log = get_email_log(email)
    Message.objects.filter(uuid=log.message_id).update(
        created_at=timezone.now() - timedelta(minutes=minutes_ago)
    )
    return log


def test_retry_sends_logged_drafts_whose_delivery_was_lost(
    django_capture_on_commit_callbacks,
) -> None:
    stale = _queued_draft(django_capture_on_commit_callbacks, minutes_ago=31)
    fresh = _queued_draft(django_capture_on_commit_callbacks, minutes_ago=1)
    unlogged = Message.objects.create(subject="Plain djmail draft", status=Message.STATUS_DRAFT)
    Message.objects.filter(uuid=unlogged.uuid).update(
        created_at=timezone.now() - timedelta(days=30)
    )

    assert retry_failed_emails() == 1

    stale.refresh_from_db()
    fresh.refresh_from_db()
    unlogged.refresh_from_db()
    assert stale.status == "sent"
    assert fresh.status == "queued"
    # Drafts plain djmail left behind are not sent by installing the log.
    assert unlogged.status == Message.STATUS_DRAFT


def test_stale_draft_recovery_can_be_turned_off(
    settings, django_capture_on_commit_callbacks
) -> None:
    settings.BASEAPP_EMAIL_LOG_STALE_DRAFT_MINUTES = None
    stale = _queued_draft(django_capture_on_commit_callbacks, minutes_ago=600)

    assert retry_failed_emails() == 0
    stale.refresh_from_db()
    assert stale.status == "queued"


@pytest.mark.django_db(transaction=True)
def test_message_held_by_another_worker_is_not_sent_twice(monkeypatch) -> None:
    """Overlapping deliveries of one message: the worker holding it wins, the other skips."""
    # Autocommit runs on_commit at once: drop the task so the message stays a stale draft.
    monkeypatch.setattr(send_queued_messages, "delay", lambda uuids: None)
    email = make_email()
    CeleryEmailBackend().send_messages([email])
    log = get_email_log(email)
    Message.objects.filter(uuid=log.message_id).update(
        created_at=timezone.now() - timedelta(minutes=60)
    )
    locked, release = threading.Event(), threading.Event()

    def other_worker() -> None:
        try:
            with transaction.atomic():
                Message.objects.select_for_update().get(uuid=log.message_id)
                locked.set()
                release.wait(10)
        finally:
            db_connection.close()

    worker = threading.Thread(target=other_worker)
    worker.start()
    try:
        assert locked.wait(10)
        assert send_queued_messages([log.message_id]) == 0
        assert retry_failed_emails() == 0
        assert mail.outbox == []
    finally:
        release.set()
        worker.join(10)

    # Released without sending: the next run sends it, once.
    assert send_queued_messages([log.message_id]) == 1
    assert retry_failed_emails() == 0
    assert len(mail.outbox) == 1
