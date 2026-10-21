from typing import Optional

import pytest

import baseapp_core.tests.factories as f
from baseapp.email_log.models import get_email_log_model
from baseapp.email_log.services import log_channel_message, send_logged

from .helpers import make_email

EmailLog = get_email_log_model()

pytestmark = pytest.mark.django_db


def test_sms_row_has_no_djmail_message_and_reads_its_own_columns() -> None:
    related = f.UserFactory()
    log = log_channel_message(
        channel=EmailLog.Channel.SMS,
        to="+15555550100",
        body_text="Your code is 1234",
        template="auth/code",
        context={"code": "1234"},
        related=related,
        category="auth",
    )

    assert log.message is None
    assert log.channel == "sms"
    assert log.recipients == ["+15555550100"]
    assert log.to == "+15555550100"
    assert log.body_text == "Your code is 1234"
    assert log.subject == ""
    assert log.body_html == ""
    assert log.from_email == ""
    assert log.status == "queued"
    assert log.sent_at is None
    assert log.error == ""
    assert log.related_object == related
    assert "SMS" in str(log)


def test_mark_delivery() -> None:
    log = log_channel_message(channel="sms", to="+15555550100", body_text="Hi")

    log.mark_delivery("sending")
    assert EmailLog.objects.with_status("sending").get() == log

    log.mark_delivery("failed", error="Carrier rejected the number")
    log.refresh_from_db()
    assert log.status == "failed"
    assert log.error == "Carrier rejected the number"
    assert log.sent_at is None

    log.mark_delivery("sent")
    log.refresh_from_db()
    assert log.status == "sent"
    assert log.error == ""
    assert log.sent_at is not None


def test_mark_delivery_refuses_email_rows() -> None:
    log = send_logged(make_email(), idempotency_key=None)
    with pytest.raises(ValueError):
        log.mark_delivery("sent")


def test_channel_rows_are_idempotent() -> None:
    first = log_channel_message(channel="sms", to="+1", body_text="a", idempotency_key="sms-1")
    second = log_channel_message(channel="sms", to="+1", body_text="b", idempotency_key="sms-1")

    assert second == first
    assert EmailLog.objects.count() == 1


def test_channel_rows_lost_race(monkeypatch) -> None:
    first = log_channel_message(channel="sms", to="+1", body_text="a", idempotency_key="sms-1")
    calls = {"count": 0}

    def find(key: str) -> Optional["EmailLog"]:
        calls["count"] += 1
        return None if calls["count"] == 1 else EmailLog.objects.filter(idempotency_key=key).first()

    monkeypatch.setattr("baseapp.email_log.services._find_by_key", find)
    assert (
        log_channel_message(channel="sms", to="+1", body_text="b", idempotency_key="sms-1") == first
    )


def test_emails_cannot_be_logged_as_a_channel_message() -> None:
    with pytest.raises(ValueError):
        log_channel_message(channel="email", to="a@example.com", body_text="x")


def test_status_filter_spans_channels() -> None:
    email_row = send_logged(make_email(), idempotency_key=None)
    sms_row = log_channel_message(channel="sms", to="+1", body_text="x", status="sent")
    queued_sms = log_channel_message(channel="sms", to="+2", body_text="y")

    assert set(EmailLog.objects.with_status("sent")) == {email_row, sms_row}
    assert list(EmailLog.objects.with_status("queued")) == [queued_sms]


def test_email_row_whose_message_was_deleted() -> None:
    log = send_logged(make_email(), idempotency_key="kept")
    log.message.delete()
    log.refresh_from_db()

    assert log.message is None
    assert log.status is None
    assert log.subject == ""
    assert log.recipients == ["to@example.com"]
    # The key still blocks a second send.
    assert send_logged(make_email(), idempotency_key="kept") == log
