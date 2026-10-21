import pytest
from django.core import mail
from djmail.models import Message

from baseapp.email_log.backends import CeleryEmailBackend
from baseapp.email_log.models import get_email_log_model
from baseapp.email_log.services import attach_log_metadata, get_email_log
from baseapp.email_log.tasks import send_queued_messages

from .helpers import make_email

EmailLog = get_email_log_model()

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def celery_backend(settings) -> None:
    settings.EMAIL_BACKEND = "baseapp.email_log.backends.CeleryEmailBackend"


def test_row_is_written_before_the_worker_runs(django_capture_on_commit_callbacks) -> None:
    email = attach_log_metadata(make_email(cc=["cc@example.com"]), category="billing")

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        assert email.send() == 1

    log = get_email_log(email)
    assert log.status == "queued"
    assert log.cc == ["cc@example.com"]
    assert mail.outbox == []
    assert len(callbacks) == 1

    # The transaction commits: the worker delivers (eager in the test settings).
    callbacks[0]()
    log.refresh_from_db()
    assert log.status == "sent"
    assert len(mail.outbox) == 1


def test_repeated_keys_and_low_priority_are_not_queued(django_capture_on_commit_callbacks) -> None:
    attach_log_metadata(make_email(), idempotency_key="k")
    first = attach_log_metadata(make_email(), idempotency_key="k")
    again = attach_log_metadata(make_email(), idempotency_key="k")
    low = make_email()
    low.priority = Message.PRIORITY_LOW

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        queued = CeleryEmailBackend().send_messages([first, again, low])

    assert queued == 2
    assert len(callbacks) == 1
    assert len(mail.outbox) == 1
    assert get_email_log(again) == get_email_log(first)
    assert get_email_log(low).message.status == Message.STATUS_PENDING


def test_nothing_to_queue(django_capture_on_commit_callbacks) -> None:
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        assert CeleryEmailBackend().send_messages([]) == 0
    assert callbacks == []


def test_worker_skips_messages_no_longer_drafts() -> None:
    message = Message.objects.create(subject="Done", status=Message.STATUS_SENT)

    assert send_queued_messages([message.uuid, "missing"]) == 0
    assert mail.outbox == []


def test_worker_transport_error_is_visible(
    failing_transport, django_capture_on_commit_callbacks
) -> None:
    email = make_email()
    with django_capture_on_commit_callbacks(execute=True):
        email.send()

    log = get_email_log(email)
    log.refresh_from_db()
    assert log.status == "failed"
    assert "SMTPException" in log.error
