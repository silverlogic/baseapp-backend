"""
djmail backends that also write the email log.

Use one of them as ``EMAIL_BACKEND`` in place of djmail's; ``DJMAIL_REAL_BACKEND`` still
names the transport. Every email gets a djmail ``Message`` and a log row, written together
before anything is sent, so the row exists (and an idempotency key is taken) even when the
transport fails.
"""

from typing import Any, Sequence

from django.core.mail import EmailMessage
from django.db import transaction
from djmail import core as djmail_core
from djmail.backends import celery as djmail_celery
from djmail.backends import default as djmail_default

from .services import (
    create_message_log,
    deliver_message,
    hold_low_priority,
    is_low_priority,
)


class EmailLogBackendMixin:
    def __init__(self, *args: Any, transport: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # The connection delivering the messages; None is DJMAIL_REAL_BACKEND.
        self.transport = transport


class EmailBackend(EmailLogBackendMixin, djmail_default.EmailBackend):
    """djmail's synchronous backend, plus the log row and visible transport errors."""

    def send_messages(self, email_messages: Sequence[EmailMessage]) -> int:
        if not email_messages:
            return 0

        # Store everything first, as djmail does; a repeated idempotency key yields None.
        stored = [(email, create_message_log(email)) for email in email_messages]
        stored = [(email, message) for email, message in stored if message is not None]
        if not stored:
            return 0

        connection = self.transport or djmail_core._get_real_backend()
        connection.open()
        try:
            sent = 0
            for email, message in stored:
                if is_low_priority(email):
                    hold_low_priority(message, email.priority)
                    sent += 1
                    continue
                sent += deliver_message(message, connection)
        finally:
            connection.close()
        return sent


class CeleryEmailBackend(EmailLogBackendMixin, djmail_celery.EmailBackend):
    """
    djmail's Celery backend, plus the log row.

    Unlike djmail's, the message and its row are written in the calling process, so the row
    is there (status ``queued``) as soon as ``send()`` returns; the worker only delivers,
    once the surrounding transaction commits. Returns the number of messages queued.
    """

    def send_messages(self, email_messages: Sequence[EmailMessage]) -> int:
        if not email_messages:
            return 0

        from .tasks import send_queued_messages

        queued = 0
        uuids = []
        for email in email_messages:
            message = create_message_log(email)
            if message is None:
                continue
            queued += 1
            if is_low_priority(email):
                hold_low_priority(message, email.priority)
            else:
                uuids.append(message.uuid)

        if uuids:
            transaction.on_commit(lambda: send_queued_messages.delay(uuids))
        return queued
