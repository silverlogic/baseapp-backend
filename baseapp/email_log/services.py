import json
import logging
import sys
import traceback
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Callable, Iterator, Optional

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.mail import EmailMessage, EmailMultiAlternatives, get_connection
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, models, transaction
from django.utils.encoding import force_str
from django.utils.module_loading import import_string
from djmail import core as djmail_core
from djmail.models import Message

from .attachments import describe_attachments, read_attachment, read_stored_attachment
from .models import get_email_log_model
from .status import EmailLogStatus

if TYPE_CHECKING:
    from .models import AbstractEmailLog

logger = logging.getLogger(__name__)

# Metadata travels on the EmailMessage as a plain attribute, never as a header, and is
# removed before djmail pickles the message.
METADATA_ATTR = "baseapp_email_log_metadata"
# The row the backend wrote for a message, set on the EmailMessage once it exists.
LOG_ATTR = "baseapp_email_log"


class EmailLogError(Exception):
    pass


class ResendError(EmailLogError):
    pass


def attach_log_metadata(
    email: EmailMessage,
    *,
    template: Optional[str] = None,
    context: Optional[dict] = None,
    related: Optional[models.Model] = None,
    category: Optional[str] = None,
    sent_by: Optional[models.Model] = None,
    idempotency_key: Optional[str] = None,
    resend_of: Optional["AbstractEmailLog"] = None,
) -> EmailMessage:
    """
    Attach what the log should record about ``email`` when it is sent through one of this
    package's backends. Arguments left as ``None`` keep any value attached earlier.
    Returns ``email`` so calls can be chained.
    """
    metadata = dict(getattr(email, METADATA_ATTR, None) or {})
    values = {
        "template": template,
        "context": context,
        "related": related,
        "category": category,
        "sent_by": sent_by,
        "idempotency_key": idempotency_key,
        "resend_of": resend_of,
    }
    metadata.update({key: value for key, value in values.items() if value is not None})
    setattr(email, METADATA_ATTR, metadata)
    return email


def get_email_log(email: EmailMessage) -> Optional["AbstractEmailLog"]:
    """The log row a backend wrote (or found, for a repeated idempotency key) for ``email``."""
    return getattr(email, LOG_ATTR, None)


class _LenientJSONEncoder(DjangoJSONEncoder):
    """
    Stores anything JSON cannot represent (model instances, ...) as its ``str()``, with a
    warning: a resend renderer gets that string back, not the object.
    """

    def default(self, o: Any) -> Any:
        try:
            return super().default(o)
        except TypeError:
            logger.warning(
                "Email log context holds a %s, which is stored as its str(); pass JSON "
                "values (a pk, a dict) to re-render from it.",
                type(o).__name__,
            )
            return force_str(o)


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, cls=_LenientJSONEncoder))


def _addresses(addresses: Any) -> list[str]:
    return [force_str(address) for address in addresses or []]


def _related_fields(metadata: dict) -> dict:
    related = metadata.get("related")
    if related is not None:
        return {
            "related_content_type": ContentType.objects.get_for_model(related),
            "related_object_id": str(related.pk),
            "related_label": force_str(related)[:255],
        }
    # Already resolved (a resend copies them from the original row, whose object may be gone).
    return {
        key: metadata[key]
        for key in ("related_content_type", "related_object_id", "related_label")
        if key in metadata
    }


def _sent_by(metadata: dict) -> Optional[models.Model]:
    user = metadata.get("sent_by")
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return user


def _metadata_fields(metadata: dict) -> dict:
    return {
        "template": metadata.get("template") or "",
        "context": _json_safe(metadata.get("context") or {}),
        "category": metadata.get("category") or "",
        "sent_by": _sent_by(metadata),
        "resend_of": metadata.get("resend_of"),
        "idempotency_key": metadata.get("idempotency_key") or None,
        **_related_fields(metadata),
    }


@contextmanager
def _pickle_safe(email: EmailMessage) -> Iterator[None]:
    """
    Hide the log's attributes and the connection while djmail pickles ``email``: the
    metadata already lives in the log row, and an open connection does not pickle.
    """
    hidden = {}
    for attr in (METADATA_ATTR, LOG_ATTR):
        if hasattr(email, attr):
            hidden[attr] = getattr(email, attr)
            delattr(email, attr)
    connection = getattr(email, "connection", None)
    email.connection = None
    try:
        yield
    finally:
        email.connection = connection
        for attr, value in hidden.items():
            setattr(email, attr, value)


def _find_by_key(idempotency_key: Optional[str]) -> Optional["AbstractEmailLog"]:
    if not idempotency_key:
        return None
    return get_email_log_model().objects.filter(idempotency_key=idempotency_key).first()


def create_message_log(email: EmailMessage) -> Optional[Message]:
    """
    Store ``email`` as a djmail ``Message`` and write its log row, atomically.

    Returns the new message, or ``None`` when the email's idempotency key is already logged:
    the email must then not be sent. Either way the row is set on the email (see
    ``get_email_log``).
    """
    EmailLog = get_email_log_model()
    metadata = getattr(email, METADATA_ATTR, None) or {}
    fields = _metadata_fields(metadata)
    key = fields["idempotency_key"]

    existing = _find_by_key(key)
    if existing is None:
        try:
            with transaction.atomic():
                with _pickle_safe(email):
                    message = Message.from_email_message(email, save=True)
                log = EmailLog.objects.create(
                    message=message,
                    channel=EmailLog.Channel.EMAIL,
                    recipients=_addresses(email.to),
                    cc=_addresses(email.cc),
                    bcc=_addresses(email.bcc),
                    reply_to=_addresses(email.reply_to),
                    attachments=describe_attachments(email, store=False),
                    **fields,
                )
        except IntegrityError:
            # Lost a race on the idempotency key: the other sender's row wins.
            existing = _find_by_key(key)
            if existing is None:
                raise

    if existing is not None:
        logger.info("Email with idempotency key %r already logged; not sending it again.", key)
        setattr(email, LOG_ATTR, existing)
        return None

    if getattr(settings, "BASEAPP_EMAIL_LOG_STORE_ATTACHMENTS", False) and log.attachments:
        log.attachments = describe_attachments(email, store=True)
        log.save(update_fields=["attachments", "modified"])

    setattr(email, LOG_ATTR, log)
    return message


def is_low_priority(email: EmailMessage) -> bool:
    """djmail holds back messages with a low ``priority`` for its periodic task."""
    priority = getattr(email, "priority", None)
    return priority is not None and priority <= Message.PRIORITY_LOW


def hold_low_priority(message: Message, priority: int) -> None:
    """Leave ``message`` pending for the periodic task, as djmail does."""
    message.priority = priority
    message.status = Message.STATUS_PENDING
    message.save(update_fields=["priority", "status"])


def record_failure(message: Message, error: str) -> None:
    """
    Mark ``message`` failed with ``error`` (a traceback) and count the attempt, so
    ``status`` and ``error`` tell the truth and the retry task picks it up.
    """
    message.exception = error
    message.status = Message.STATUS_FAILED
    message.retry_count += 1
    message.save(update_fields=["exception", "status", "retry_count"])


def open_connection(connection: Any) -> str:
    """
    Open ``connection``, returning ``""``, or the traceback when it cannot be opened.

    djmail's real backend never fails silently, so an unreachable SMTP server raises here,
    before any message reaches ``_safe_send_message``. The caller records the traceback on
    each message instead of letting it escape and leave them queued.
    """
    try:
        connection.open()
    except Exception:
        logger.exception("Could not open the email connection")
        return traceback.format_exc()
    return ""


def close_connection(connection: Any) -> None:
    """Close ``connection``. The messages are already sent or failed, so errors are only logged."""
    try:
        connection.close()
    except Exception:
        logger.exception("Could not close the email connection")


def deliver_message(message: Message, connection: Any) -> int:
    """
    Send a stored djmail message through the open ``connection`` with djmail's own
    machinery, and make a transport error count as a failure.

    djmail records the traceback of an exception in ``Message.exception`` but leaves the
    status untouched (a draft stays a draft, so it is never retried) and does not count
    the attempt. Here it goes through ``record_failure``.
    """
    message.exception = ""
    sent = djmail_core._safe_send_message(message, connection)
    if not sent and message.exception:
        record_failure(message, message.exception)
    return sent


def logging_connection(connection: Any = None) -> Any:
    """
    ``connection`` (default: ``EMAIL_BACKEND``) if it is one of this package's backends.
    Plain djmail backends are swapped for their logging counterpart (delivering through
    ``DJMAIL_REAL_BACKEND``, so djmail does not store the message twice). Any other
    connection becomes the transport of this package's sync backend, so the email is
    logged whatever the project's (or the test runner's) ``EMAIL_BACKEND`` is.
    """
    from djmail.backends.base import BaseEmailBackend as DjmailBaseBackend

    from .backends import CeleryEmailBackend, EmailBackend, EmailLogBackendMixin

    connection = connection or get_connection()
    if isinstance(connection, EmailLogBackendMixin):
        return connection
    # Looked up, not imported: importing djmail.backends.celery creates djmail's Celery app
    # and makes it the current app. A connection of that class means it is already loaded.
    djmail_celery = sys.modules.get("djmail.backends.celery")
    if djmail_celery is not None and isinstance(connection, djmail_celery.EmailBackend):
        return CeleryEmailBackend()
    if isinstance(connection, DjmailBaseBackend):
        return EmailBackend()
    return EmailBackend(transport=connection)


def send_logged(
    email: EmailMessage,
    *,
    idempotency_key: Optional[str],
    connection: Any = None,
    **metadata: Any,
) -> "AbstractEmailLog":
    """
    Send ``email`` once per ``idempotency_key`` and return its log row.

    When the key is already logged, the existing row is returned and nothing is sent. Two
    concurrent calls with the same key are settled by the key's unique constraint: one
    sends, the other gets the winner's row. ``metadata`` takes the keyword arguments of
    ``attach_log_metadata``.
    """
    existing = _find_by_key(idempotency_key)
    if existing is not None:
        return existing
    attach_log_metadata(email, idempotency_key=idempotency_key, **metadata)
    logging_connection(connection).send_messages([email])
    return get_email_log(email)


def log_channel_message(
    *,
    channel: str,
    to: str,
    body_text: str,
    status: str = EmailLogStatus.QUEUED,
    template: Optional[str] = None,
    context: Optional[dict] = None,
    related: Optional[models.Model] = None,
    category: Optional[str] = None,
    sent_by: Optional[models.Model] = None,
    idempotency_key: Optional[str] = None,
) -> "AbstractEmailLog":
    """
    Log a message of another channel (SMS, push, ...), which has no djmail message. The
    caller delivers it and records the outcome with ``log.mark_delivery(...)``. A repeated
    ``idempotency_key`` returns the existing row.
    """
    EmailLog = get_email_log_model()
    if channel == EmailLog.Channel.EMAIL:
        raise ValueError("Emails are logged by sending them through the email backend.")
    existing = _find_by_key(idempotency_key)
    if existing is not None:
        return existing
    fields = _metadata_fields(
        {
            "template": template,
            "context": context,
            "related": related,
            "category": category,
            "sent_by": sent_by,
            "idempotency_key": idempotency_key,
        }
    )
    try:
        with transaction.atomic():
            return EmailLog.objects.create(
                channel=channel,
                recipients=[to],
                delivery_to=to,
                delivery_body_text=body_text,
                delivery_status=EmailLogStatus(status).value,
                **fields,
            )
    except IntegrityError:
        existing = _find_by_key(idempotency_key)
        if existing is None:
            raise
        return existing


def get_renderer() -> Optional[Callable[[str, dict], dict]]:
    """
    ``BASEAPP_EMAIL_LOG_RENDERER``: a callable (or its dotted path) taking
    ``(template, context)`` and returning a dict with any of ``subject``, ``body_text`` and
    ``body_html``. ``None`` when not configured.
    """
    renderer = getattr(settings, "BASEAPP_EMAIL_LOG_RENDERER", None)
    if isinstance(renderer, str):
        renderer = import_string(renderer)
    return renderer


def _attach_from(
    email: EmailMessage, log: "AbstractEmailLog", original: Optional[EmailMessage]
) -> None:
    if original is not None:
        email.attachments = list(original.attachments)
        return
    for entry in log.attachments or []:
        content = read_stored_attachment(entry)
        if content is not None:
            email.attach(entry.get("name") or None, content, entry.get("content_type"))


def email_message_for(log: "AbstractEmailLog") -> EmailMessage:
    """
    The email of ``log``, ready to send again: djmail's pickled message when it is there.
    Otherwise it is rebuilt from djmail's columns (subject, bodies, from), the row's To,
    cc, bcc and reply-to, and the attachments in the attachment storage; custom headers are
    then lost.

    Raises ``ResendError`` for rows of other channels, when the djmail message is gone,
    and when an attachment the row lists cannot be read.
    """
    if log.channel != log.Channel.EMAIL:
        raise ResendError("Only email rows have an email message.")
    original = log.get_email_message()
    if original is not None:
        return original
    if log.message_id is None:
        raise ResendError("The original message is no longer stored.")

    message = log.message
    email = EmailMultiAlternatives(
        subject=message.subject,
        body=message.body_text,
        from_email=message.from_email or None,
        to=log.recipients or [a for a in message.to_email.split(",") if a],
        cc=log.cc,
        bcc=log.bcc,
        reply_to=log.reply_to,
    )
    if message.body_html:
        email.attach_alternative(message.body_html, "text/html")
    for index, entry in enumerate(log.attachments or []):
        attachment = read_attachment(log, index)
        if attachment is None:
            raise ResendError(f"The attachment {entry.get('name') or index!r} is no longer stored.")
        email.attach(*attachment)
    return email


def _render(
    log: "AbstractEmailLog", original: Optional[EmailMessage], renderer: Callable[[str, dict], dict]
) -> EmailMessage:
    rendered = renderer(log.template, log.context) or {}
    email = EmailMultiAlternatives(
        subject=rendered.get("subject", log.subject),
        body=rendered.get("body_text", log.body_text),
        from_email=log.from_email or None,
        to=log.recipients,
        cc=log.cc,
        bcc=log.bcc,
        reply_to=log.reply_to,
        headers=dict(original.extra_headers) if original is not None else None,
    )
    body_html = rendered.get("body_html", log.body_html)
    if body_html:
        email.attach_alternative(body_html, "text/html")
    _attach_from(email, log, original)
    return email


def resend(
    log: "AbstractEmailLog",
    *,
    to: Optional[list[str]] = None,
    sent_by: Optional[models.Model] = None,
    connection: Any = None,
) -> "AbstractEmailLog":
    """
    Send the email of ``log`` again as a new djmail message, and return the new row (its
    ``resend_of`` is ``log``).

    With ``BASEAPP_EMAIL_LOG_RENDERER`` configured and a template on the row, the message
    is re-rendered from the template and the stored context. Otherwise the original is sent
    again as it was (see ``email_message_for``). ``to`` replaces the To recipients; cc and
    bcc are kept. Raises ``ResendError`` for other channels, for an empty ``to``, and when
    there is nothing left to send.
    """
    if log.channel != log.Channel.EMAIL:
        raise ResendError("Only email rows can be resent.")
    if isinstance(to, str):
        to = [to]
    if to is not None and not to:
        raise ResendError("Give at least one address to resend to.")

    renderer = get_renderer()
    if renderer is not None and log.template:
        email = _render(log, log.get_email_message(), renderer)
    else:
        email = email_message_for(log)
    if to is not None:
        email.to = list(to)

    setattr(
        email,
        METADATA_ATTR,
        {
            "template": log.template,
            "context": log.context,
            "category": log.category,
            "sent_by": sent_by,
            "resend_of": log,
            "related_content_type": log.related_content_type,
            "related_object_id": log.related_object_id,
            "related_label": log.related_label,
        },
    )
    logging_connection(connection).send_messages([email])
    return get_email_log(email)
