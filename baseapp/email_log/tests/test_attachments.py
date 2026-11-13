from email.mime.text import MIMEText
from pathlib import Path

import pytest
from djmail.models import Message

from baseapp.email_log.attachments import read_attachment
from baseapp.email_log.models import get_email_log_model
from baseapp.email_log.services import send_logged

from .helpers import make_email

EmailLog = get_email_log_model()

pytestmark = pytest.mark.django_db


def _send_with_attachments() -> "EmailLog":
    email = make_email()
    email.attach("invoice.pdf", b"%PDF", "application/pdf")
    mime = MIMEText("mime body")
    mime.add_header("Content-Disposition", "attachment", filename="notes.txt")
    email.attach(mime)
    return send_logged(email, idempotency_key=None)


def _drop_pickle(log: "EmailLog") -> None:
    Message.objects.filter(pk=log.message_id).update(data="")
    log.refresh_from_db()


def test_reads_from_djmails_message() -> None:
    log = _send_with_attachments()

    assert read_attachment(log, 0) == ("invoice.pdf", b"%PDF", "application/pdf")
    assert read_attachment(log, 1) == ("notes.txt", b"mime body", "text/plain")


def test_reads_from_the_storage_without_djmails_pickle(attachment_storage: Path) -> None:
    log = _send_with_attachments()
    _drop_pickle(log)

    assert log.get_email_message() is None
    assert read_attachment(log, 0) == ("invoice.pdf", b"%PDF", "application/pdf")
    assert read_attachment(log, 1) == ("notes.txt", b"mime body", "text/plain")


def test_reads_from_the_storage_once_the_message_is_gone(attachment_storage: Path) -> None:
    log = _send_with_attachments()
    Message.objects.filter(pk=log.message_id).delete()
    log.refresh_from_db()

    assert read_attachment(log, 0) == ("invoice.pdf", b"%PDF", "application/pdf")


def test_none_when_nothing_holds_it(attachment_storage: Path) -> None:
    log = _send_with_attachments()

    assert read_attachment(log, 2) is None
    assert read_attachment(log, -1) is None

    _drop_pickle(log)
    (attachment_storage / log.attachments[0]["path"]).unlink()
    assert read_attachment(log, 0) is None


def test_none_without_pickle_or_stored_copy() -> None:
    log = _send_with_attachments()
    _drop_pickle(log)

    assert log.attachments[0] == {
        "name": "invoice.pdf",
        "content_type": "application/pdf",
        "size": 4,
    }
    assert read_attachment(log, 0) is None


def test_unreadable_pickle_falls_back_to_the_storage(attachment_storage: Path) -> None:
    log = _send_with_attachments()
    Message.objects.filter(pk=log.message_id).update(data="not a pickle")
    log.refresh_from_db()

    assert log.get_email_message() is None
    assert read_attachment(log, 0) == ("invoice.pdf", b"%PDF", "application/pdf")
