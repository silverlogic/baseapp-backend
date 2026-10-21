from smtplib import SMTPException
from typing import Optional

from django.core.mail import EmailMultiAlternatives
from django.core.mail.backends.base import BaseEmailBackend

TRANSPORT_ERROR = "Connection refused by the test transport"


UNREACHABLE_ERROR = "Connection refused by the unreachable test transport"


class FailingBackend(BaseEmailBackend):
    """A transport whose every send raises, like a server rejecting the message."""

    def send_messages(self, email_messages) -> int:
        raise SMTPException(TRANSPORT_ERROR)


class UnreachableBackend(BaseEmailBackend):
    """A transport that cannot connect: ``open()`` raises, as SMTP's does for a down server."""

    def open(self) -> bool:
        raise ConnectionRefusedError(111, UNREACHABLE_ERROR)

    def send_messages(self, email_messages) -> int:
        raise AssertionError("send_messages must not be reached when open() failed")


class ClosingFailsBackend(BaseEmailBackend):
    """Delivers into ``mail.outbox`` but raises when closed, as SMTP's ``quit`` can."""

    def send_messages(self, email_messages) -> int:
        from django.core import mail

        mail.outbox.extend(email_messages)
        return len(email_messages)

    def close(self) -> None:
        raise SMTPException("QUIT failed")


class NothingSentBackend(BaseEmailBackend):
    """A transport that reports zero messages sent without raising."""

    def send_messages(self, email_messages) -> int:
        return 0


def make_email(
    *,
    subject: str = "Your invoice",
    body: str = "Plain body",
    html: Optional[str] = "<p>HTML body</p>",
    to: tuple = ("to@example.com",),
    **kwargs,
) -> EmailMultiAlternatives:
    email = EmailMultiAlternatives(
        subject=subject, body=body, from_email="from@example.com", to=list(to), **kwargs
    )
    if html:
        email.attach_alternative(html, "text/html")
    return email


def render_template(template: str, context: dict) -> dict:
    """A test renderer for resend: renders the context into the bodies."""
    return {
        "subject": f"[{template}] Hello {context.get('name', '')}",
        "body_text": f"Hi {context.get('name', '')}, re-rendered",
        "body_html": f"<p>Hi {context.get('name', '')}, re-rendered</p>",
    }
