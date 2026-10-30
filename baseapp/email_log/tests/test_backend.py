from email.mime.text import MIMEText
from typing import Any

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.mail import EmailMessage, get_connection, send_mail
from djmail.models import Message

import baseapp_core.tests.factories as f
from baseapp.email_log.attachments import read_stored_attachment
from baseapp.email_log.backends import EmailBackend
from baseapp.email_log.models import get_email_log_model
from baseapp.email_log.services import METADATA_ATTR, attach_log_metadata, get_email_log

from .helpers import make_email

EmailLog = get_email_log_model()

pytestmark = pytest.mark.django_db


def test_every_email_is_logged_without_metadata() -> None:
    sent = send_mail("Hello", "Body", "from@example.com", ["a@example.com", "b@example.com"])

    assert sent == 1
    assert len(mail.outbox) == 1
    log = EmailLog.objects.get()
    message = Message.objects.get()
    assert log.message == message
    assert log.channel == EmailLog.Channel.EMAIL
    assert log.recipients == ["a@example.com", "b@example.com"]
    assert log.template == ""
    assert log.context == {}
    assert log.idempotency_key is None
    # Read through the log, stored once by djmail.
    assert log.subject == message.subject == "Hello"
    assert log.body_text == "Body"
    assert log.from_email == "from@example.com"
    assert log.to == "a@example.com,b@example.com"
    assert log.status == "sent"
    assert log.sent_at == message.sent_at is not None
    assert log.error == ""


def test_cc_bcc_and_reply_to_are_captured() -> None:
    email = make_email(
        to=("to@example.com",),
        cc=["cc1@example.com", "cc2@example.com"],
        bcc=["bcc@example.com"],
        reply_to=["reply@example.com"],
    )
    email.send()

    log = get_email_log(email)
    log.refresh_from_db()
    assert log.recipients == ["to@example.com"]
    assert log.cc == ["cc1@example.com", "cc2@example.com"]
    assert log.bcc == ["bcc@example.com"]
    assert log.reply_to == ["reply@example.com"]
    assert log.body_html == "<p>HTML body</p>"
    # djmail itself keeps only the To addresses.
    assert log.message.to_email == "to@example.com"
    assert mail.outbox[0].bcc == ["bcc@example.com"]


def test_metadata_is_recorded() -> None:
    user = f.UserFactory()
    related = f.UserFactory(first_name="Related")
    email = attach_log_metadata(
        make_email(),
        template="invoices/paid",
        context={"name": "Ada", "user": related, "amount": 12},
        related=related,
        category="billing",
        sent_by=user,
        idempotency_key="invoice-1-paid",
    )
    email.send()

    log = EmailLog.objects.get()
    assert log.template == "invoices/paid"
    # Values JSON cannot hold are stored as their text.
    assert log.context == {"name": "Ada", "user": str(related), "amount": 12}
    assert log.related_content_type == ContentType.objects.get_for_model(related)
    assert log.related_object_id == str(related.pk)
    assert log.related_object == related
    assert log.related_label == str(related)
    assert log.category == "billing"
    assert log.sent_by == user
    assert log.idempotency_key == "invoice-1-paid"
    assert list(EmailLog.objects.for_object(related)) == [log]


def test_metadata_arguments_merge_across_calls() -> None:
    email = attach_log_metadata(make_email(), template="welcome", category="auth")
    attach_log_metadata(email, category="onboarding")

    assert getattr(email, METADATA_ATTR) == {"template": "welcome", "category": "onboarding"}


def test_anonymous_sender_is_not_recorded() -> None:
    from django.contrib.auth.models import AnonymousUser

    attach_log_metadata(make_email(), sent_by=AnonymousUser()).send()

    assert EmailLog.objects.get().sent_by is None


def test_metadata_is_not_pickled_into_djmail() -> None:
    user = f.UserFactory()
    email = attach_log_metadata(make_email(), context={"secret": "x"}, sent_by=user)
    email.send()

    stored = Message.objects.get().get_email_message()
    assert not hasattr(stored, METADATA_ATTR)
    assert stored.connection is None
    # The caller's email keeps its metadata and gets its row.
    assert getattr(email, METADATA_ATTR)["context"] == {"secret": "x"}
    assert get_email_log(email) == EmailLog.objects.get()


def test_attachments_are_described() -> None:
    email = make_email()
    email.attach("invoice.pdf", b"%PDF-1.4 content", "application/pdf")
    email.attach("notes.txt", "some text", "text/plain")
    email.send()

    log = EmailLog.objects.get()
    assert log.attachments == [
        {"name": "invoice.pdf", "content_type": "application/pdf", "size": 16},
        {"name": "notes.txt", "content_type": "text/plain", "size": 9},
    ]
    # djmail still keeps its own copy, so it can retry.
    assert len(Message.objects.get().get_email_message().attachments) == 2


def test_attachments_are_stored_when_enabled(attachment_storage) -> None:
    email = make_email()
    email.attach("invoice.pdf", b"%PDF-1.4 content", "application/pdf")
    mime = MIMEText("mime body")
    mime.add_header("Content-Disposition", "attachment", filename="mime.txt")
    email.attach(mime)
    email.send()

    log = EmailLog.objects.get()
    pdf, text = log.attachments
    assert pdf["path"].startswith("email_log/")
    assert pdf["path"].endswith("/invoice.pdf")
    assert read_stored_attachment(pdf) == b"%PDF-1.4 content"
    assert text["name"] == "mime.txt"
    assert read_stored_attachment(text) == b"mime body"
    assert (attachment_storage / pdf["path"]).exists()


def test_attachment_storage_failure_does_not_stop_the_email(
    attachment_storage, monkeypatch
) -> None:
    def broken_store(*args: Any, **kwargs: Any) -> str:
        raise OSError("disk full")

    monkeypatch.setattr("baseapp.email_log.attachments._store", broken_store)
    email = make_email()
    email.attach("invoice.pdf", b"content", "application/pdf")
    email.send()

    assert len(mail.outbox) == 1
    assert EmailLog.objects.get().attachments == [
        {"name": "invoice.pdf", "content_type": "application/pdf", "size": 7}
    ]


def test_attachment_storage_as_dotted_path(settings) -> None:
    from django.core.files.storage import FileSystemStorage

    from baseapp.email_log.attachments import get_attachment_storage

    settings.BASEAPP_EMAIL_LOG_ATTACHMENT_STORAGE = "django.core.files.storage.FileSystemStorage"
    assert isinstance(get_attachment_storage(), FileSystemStorage)


def test_several_messages_in_one_call() -> None:
    connection = get_connection()
    sent = connection.send_messages(
        [
            make_email(subject="One"),
            make_email(subject="Two"),
            EmailMessage("Three", "x", to=["c@example.com"]),
        ]
    )

    assert sent == 3
    assert len(mail.outbox) == 3
    assert set(EmailLog.objects.values_list("message__subject", flat=True)) == {
        "One",
        "Two",
        "Three",
    }


def test_no_messages() -> None:
    assert EmailBackend().send_messages([]) == 0
    assert not EmailLog.objects.exists()


def test_low_priority_messages_wait_for_the_periodic_task() -> None:
    email = make_email()
    email.priority = Message.PRIORITY_LOW
    sent = get_connection().send_messages([email])

    assert sent == 1
    assert mail.outbox == []
    log = get_email_log(email)
    log.refresh_from_db()
    assert log.message.status == Message.STATUS_PENDING
    assert log.status == "queued"


def test_to_falls_back_to_the_rows_recipients() -> None:
    email = make_email(to=("a@example.com", "b@example.com"))
    email.send()
    log = get_email_log(email)
    assert log.to == "a@example.com,b@example.com"

    log.message.delete()
    log.refresh_from_db()
    assert log.to == "a@example.com,b@example.com"
    assert str(log) == "Email to a@example.com,b@example.com: -"


def test_str_of_a_bcc_only_email_names_its_recipients() -> None:
    email = make_email(to=(), bcc=["hidden@example.com"])
    email.send()

    assert get_email_log(email).to == ""
    assert str(get_email_log(email)) == "Email to hidden@example.com: Your invoice"


def test_context_values_json_cannot_hold_are_stored_as_strings_with_a_warning(caplog) -> None:
    class Invoice:
        def __str__(self) -> str:
            return "Invoice 7"

    email = attach_log_metadata(make_email(), context={"invoice": Invoice(), "number": 7})
    with caplog.at_level("WARNING", logger="baseapp.email_log.services"):
        email.send()

    assert get_email_log(email).context == {"invoice": "Invoice 7", "number": 7}
    assert "holds a Invoice" in caplog.text
