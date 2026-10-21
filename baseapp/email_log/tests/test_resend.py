from pathlib import Path

import pytest
from django.core import mail
from djmail.models import Message

import baseapp_core.tests.factories as f
from baseapp.email_log.models import get_email_log_model
from baseapp.email_log.services import (
    ResendError,
    log_channel_message,
    resend,
    send_logged,
)

from .helpers import make_email

EmailLog = get_email_log_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def original() -> "EmailLog":
    email = make_email(cc=["cc@example.com"], reply_to=["reply@example.com"])
    email.attach("invoice.pdf", b"%PDF", "application/pdf")
    email.extra_headers["X-Tag"] = "invoice"
    related = f.UserFactory()
    return send_logged(
        email,
        idempotency_key="invoice-1",
        template="invoices/paid",
        context={"name": "Ada"},
        related=related,
        category="billing",
    )


def test_resend_sends_the_stored_message_again(original) -> None:
    admin = f.UserFactory()
    copy = resend(original, sent_by=admin)

    assert copy.pk != original.pk
    assert copy.resend_of == original
    assert list(original.resends.all()) == [copy]
    assert copy.message_id != original.message_id
    assert copy.idempotency_key is None
    assert copy.sent_by == admin
    assert copy.template == "invoices/paid"
    assert copy.context == {"name": "Ada"}
    assert copy.category == "billing"
    assert copy.related_object == original.related_object
    assert copy.related_label == original.related_label
    assert copy.cc == ["cc@example.com"]
    assert copy.subject == original.subject
    assert copy.body_html == original.body_html
    assert copy.status == "sent"
    assert len(mail.outbox) == 2
    resent = mail.outbox[1]
    assert resent.attachments[0][0] == "invoice.pdf"
    assert resent.extra_headers["X-Tag"] == "invoice"


def test_resend_re_renders_with_a_renderer(original, settings) -> None:
    settings.BASEAPP_EMAIL_LOG_RENDERER = "baseapp.email_log.tests.helpers.render_template"
    copy = resend(original)

    assert copy.subject == "[invoices/paid] Hello Ada"
    assert copy.body_text == "Hi Ada, re-rendered"
    assert copy.body_html == "<p>Hi Ada, re-rendered</p>"
    assert copy.recipients == original.recipients
    assert copy.cc == ["cc@example.com"]
    assert copy.reply_to == ["reply@example.com"]
    assert copy.from_email == "from@example.com"
    resent = mail.outbox[1]
    assert resent.attachments[0][0] == "invoice.pdf"
    assert resent.extra_headers["X-Tag"] == "invoice"


def test_renderer_can_be_a_callable(original, settings) -> None:
    settings.BASEAPP_EMAIL_LOG_RENDERER = lambda template, context: {"subject": "Only subject"}
    copy = resend(original)

    assert copy.subject == "Only subject"
    # Keys the renderer leaves out fall back to the stored message.
    assert copy.body_text == original.body_text


def test_rows_without_template_resend_the_stored_message(settings) -> None:
    settings.BASEAPP_EMAIL_LOG_RENDERER = "baseapp.email_log.tests.helpers.render_template"
    log = send_logged(make_email(subject="Plain"), idempotency_key=None)

    assert resend(log).subject == "Plain"


def test_resend_after_the_message_is_gone_needs_a_renderer(original, settings) -> None:
    Message.objects.filter(pk=original.message_id).delete()
    original.refresh_from_db()

    with pytest.raises(ResendError):
        resend(original)

    settings.BASEAPP_EMAIL_LOG_RENDERER = "baseapp.email_log.tests.helpers.render_template"
    copy = resend(original)
    assert copy.subject == "[invoices/paid] Hello Ada"
    assert copy.recipients == ["to@example.com"]
    # Without djmail's copy, attachments can only come from the attachment storage, and
    # these were not stored.
    assert copy.attachments == []


def test_resend_reattaches_stored_files_when_the_message_is_gone(
    settings, attachment_storage: Path
) -> None:
    settings.BASEAPP_EMAIL_LOG_RENDERER = "baseapp.email_log.tests.helpers.render_template"
    email = make_email()
    email.attach("invoice.pdf", b"%PDF", "application/pdf")
    log = send_logged(email, idempotency_key=None, template="invoices/paid", context={})
    Message.objects.filter(pk=log.message_id).delete()
    log.refresh_from_db()

    resend(log)

    assert mail.outbox[-1].attachments == [("invoice.pdf", b"%PDF", "application/pdf")]


def test_other_channels_cannot_be_resent() -> None:
    log = log_channel_message(channel="sms", to="+1", body_text="x")
    with pytest.raises(ResendError):
        resend(log)


def test_resend_of_a_failed_email(failing_transport, settings) -> None:
    log = send_logged(make_email(), idempotency_key=None)
    assert log.status == "failed"

    settings.DJMAIL_REAL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    copy = resend(log)

    assert copy.status == "sent"
    log.refresh_from_db()
    assert log.status == "failed"
