from typing import Any, Callable, Optional

import pytest
from django.core import mail
from django.core.mail import get_connection
from djmail.models import Message

import baseapp_core.tests.factories as f
from baseapp.email_log.backends import CeleryEmailBackend, EmailBackend
from baseapp.email_log.models import get_email_log_model
from baseapp.email_log.services import (
    attach_log_metadata,
    get_email_log,
    logging_connection,
    send_logged,
)

from .conftest import LOCMEM_BACKEND
from .helpers import make_email

EmailLog = get_email_log_model()

pytestmark = pytest.mark.django_db


def test_send_logged_sends_once_per_key() -> None:
    user = f.UserFactory()
    first = send_logged(make_email(), idempotency_key="order-1", category="orders", sent_by=user)
    second = send_logged(make_email(subject="Again"), idempotency_key="order-1")

    assert second == first
    assert len(mail.outbox) == 1
    assert Message.objects.count() == 1
    assert first.category == "orders"
    assert first.sent_by == user
    assert first.status == "sent"


def test_send_logged_without_key_always_sends() -> None:
    send_logged(make_email(), idempotency_key=None)
    send_logged(make_email(), idempotency_key=None)

    assert len(mail.outbox) == 2
    assert EmailLog.objects.count() == 2


def test_lost_race_returns_the_winners_row(monkeypatch) -> None:
    """
    Two senders both see the key free; the unique constraint settles it. The loser's
    message and row are rolled back and nothing is sent twice.
    """
    winner = send_logged(make_email(), idempotency_key="race")
    assert len(mail.outbox) == 1

    # The loser's look-ups ran before the winner committed: they all miss.
    monkeypatch.setattr("baseapp.email_log.services._find_by_key", _miss_then_find())
    loser = send_logged(make_email(subject="Loser"), idempotency_key="race")

    assert loser == winner
    assert len(mail.outbox) == 1
    assert Message.objects.count() == 1
    assert EmailLog.objects.count() == 1


def _miss_then_find() -> Callable[[str], Optional["EmailLog"]]:
    """``_find_by_key`` that misses twice (send_logged's and the backend's checks)."""
    calls = {"count": 0}

    def find(key: str) -> Optional["EmailLog"]:
        calls["count"] += 1
        if calls["count"] <= 2:
            return None
        return EmailLog.objects.filter(idempotency_key=key).first()

    return find


def test_integrity_errors_unrelated_to_the_key_propagate(monkeypatch) -> None:
    from django.db import IntegrityError

    def broken_create(*args: Any, **kwargs: Any) -> "EmailLog":
        raise IntegrityError("something else")

    monkeypatch.setattr(EmailLog.objects, "create", broken_create)
    with pytest.raises(IntegrityError):
        send_logged(make_email(), idempotency_key="other")
    assert not Message.objects.exists()


def test_backend_skips_repeated_keys_too() -> None:
    attach_log_metadata(make_email(), idempotency_key="welcome-1").send()
    again = attach_log_metadata(make_email(), idempotency_key="welcome-1")
    sent = again.send()

    assert sent == 0
    assert len(mail.outbox) == 1
    assert get_email_log(again) == EmailLog.objects.get()


def test_send_logged_logs_whatever_the_email_backend(settings) -> None:
    # e.g. the test runner's locmem backend, or a project not yet using the log backend.
    settings.EMAIL_BACKEND = LOCMEM_BACKEND
    log = send_logged(make_email(), idempotency_key="k")

    assert log.status == "sent"
    assert len(mail.outbox) == 1


def test_send_logged_with_explicit_connection() -> None:
    connection = get_connection(LOCMEM_BACKEND)
    log = send_logged(make_email(), idempotency_key="k", connection=connection)
    assert log.message.status == Message.STATUS_SENT

    log_backend = EmailBackend()
    second = send_logged(make_email(), idempotency_key="k2", connection=log_backend)
    assert second.status == "sent"
    assert len(mail.outbox) == 2


@pytest.mark.parametrize(
    "djmail_backend, logging_backend",
    [
        ("djmail.backends.default.EmailBackend", EmailBackend),
        ("djmail.backends.celery.EmailBackend", CeleryEmailBackend),
    ],
)
def test_plain_djmail_backend_is_not_stacked(settings, djmail_backend, logging_backend) -> None:
    settings.EMAIL_BACKEND = djmail_backend

    connection = logging_connection()

    assert type(connection) is logging_backend
    assert connection.transport is None


def test_send_logged_under_plain_djmail_stores_the_message_once(settings) -> None:
    settings.EMAIL_BACKEND = "djmail.backends.default.EmailBackend"
    log = send_logged(make_email(), idempotency_key="once")

    assert Message.objects.get() == log.message
    assert len(mail.outbox) == 1
