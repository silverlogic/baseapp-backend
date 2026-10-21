import logging
from datetime import timedelta
from typing import Iterable, Optional

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from djmail import core as djmail_core
from djmail.models import Message

from .attachments import delete_stored_attachments
from .models import get_email_log_model
from .services import deliver_message

logger = logging.getLogger(__name__)

CHUNK_SIZE = 100


def _chunks(values: list, size: int = CHUNK_SIZE) -> Iterable[list]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _deliver(uuids: list[str]) -> int:
    """
    Deliver the djmail messages ``uuids`` in order through ``DJMAIL_REAL_BACKEND``. The ids
    are collected up front because delivering changes the status the caller filtered on.
    """
    if not uuids:
        return 0
    connection = djmail_core._get_real_backend()
    connection.open()
    try:
        sent = 0
        for chunk in _chunks(uuids):
            messages = {message.uuid: message for message in Message.objects.filter(uuid__in=chunk)}
            for uuid in chunk:
                if uuid in messages:
                    sent += deliver_message(messages[uuid], connection)
        return sent
    finally:
        connection.close()


@shared_task
def send_queued_messages(message_uuids: list[str]) -> int:
    """Deliver messages queued by ``CeleryEmailBackend`` (only those still drafts)."""
    uuids = list(
        Message.objects.filter(uuid__in=message_uuids, status=Message.STATUS_DRAFT)
        .order_by("created_at")
        .values_list("uuid", flat=True)
    )
    return _deliver(uuids)


@shared_task
def retry_failed_emails() -> int:
    """
    djmail's periodic pass, with transport errors counted as failures: send the pending
    low-priority messages, discard failed messages past ``DJMAIL_MAX_RETRY_NUMBER``, and
    retry the remaining failed ones. Returns the number of messages sent.
    """
    pending = list(
        Message.objects.filter(status=Message.STATUS_PENDING)
        .order_by("-priority", "created_at")
        .values_list("uuid", flat=True)
    )
    sent = _deliver(pending)

    discarded = djmail_core._mark_discarded_messages()

    max_retries = getattr(settings, "DJMAIL_MAX_RETRY_NUMBER", 3)
    failed = list(
        Message.objects.filter(status=Message.STATUS_FAILED, retry_count__lte=max_retries)
        .order_by("-priority", "created_at")
        .values_list("uuid", flat=True)
    )
    sent += _deliver(failed)

    logger.info("Email retry: %s sent, %s discarded after %s retries", sent, discarded, max_retries)
    return sent


@shared_task
def purge_email_logs(older_than_days: Optional[int] = None) -> int:
    """
    Delete log rows created more than ``older_than_days`` days ago (default:
    ``BASEAPP_EMAIL_LOG_RETENTION_DAYS``; ``None`` keeps everything), with their djmail
    messages and stored attachments, plus djmail messages that old with no row.

    Rows with an idempotency key are kept, so their keys keep blocking duplicate sends,
    unless ``BASEAPP_EMAIL_LOG_PURGE_IDEMPOTENT`` is on. Returns the number of rows deleted.
    """
    if older_than_days is None:
        older_than_days = getattr(settings, "BASEAPP_EMAIL_LOG_RETENTION_DAYS", None)
    if older_than_days is None:
        return 0

    EmailLog = get_email_log_model()
    cutoff = timezone.now() - timedelta(days=older_than_days)

    logs = EmailLog.objects.filter(created__lt=cutoff)
    if not getattr(settings, "BASEAPP_EMAIL_LOG_PURGE_IDEMPOTENT", False):
        logs = logs.filter(idempotency_key__isnull=True)

    deleted = 0
    ids = list(logs.values_list("pk", flat=True))
    for chunk in _chunks(ids):
        rows = list(EmailLog.objects.filter(pk__in=chunk).values("message_id", "attachments"))
        with transaction.atomic():
            _, per_model = EmailLog.objects.filter(pk__in=chunk).delete()
            deleted += per_model.get(EmailLog._meta.label, 0)
            message_ids = [row["message_id"] for row in rows if row["message_id"]]
            Message.objects.filter(uuid__in=message_ids).delete()
        for row in rows:
            delete_stored_attachments(row["attachments"])

    orphans, _ = Message.objects.filter(created_at__lt=cutoff, email_log__isnull=True).delete()
    logger.info(
        "Purged %s email log rows and %s unlogged djmail messages older than %s days",
        deleted,
        orphans,
        older_than_days,
    )
    return deleted
