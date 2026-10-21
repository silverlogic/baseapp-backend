import logging
import traceback
from datetime import timedelta
from typing import Callable, Iterable, Optional

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from djmail import core as djmail_core
from djmail.models import Message

from .attachments import delete_stored_attachments
from .models import get_email_log_model
from .services import close_connection, deliver_message, open_connection, record_failure

logger = logging.getLogger(__name__)

CHUNK_SIZE = 100


def _chunks(values: list, size: int = CHUNK_SIZE) -> Iterable[list]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _for_each_claimed(uuids: list[str], eligible: Q, action: Callable[[Message], int]) -> int:
    """
    Run ``action`` on each message of ``uuids``, in order, that is still ``eligible``,
    holding its row lock until ``action`` has saved the outcome. A message another worker
    holds is skipped, and one it has dealt with meanwhile is no longer eligible, so
    overlapping runs never send the same message twice. The ids are collected up front
    because delivering changes the status the caller filtered on.
    """
    done = 0
    for uuid in uuids:
        with transaction.atomic():
            message = (
                Message.objects.select_for_update(skip_locked=True)
                .filter(eligible, uuid=uuid)
                .first()
            )
            if message is not None:
                done += action(message)
    return done


def _fail(uuids: list[str], eligible: Q, error: str) -> None:
    def fail(message: Message) -> int:
        record_failure(message, error)
        return 0

    _for_each_claimed(uuids, eligible, fail)


def _deliver(uuids: list[str], eligible: Q) -> int:
    """
    Deliver the djmail messages ``uuids`` in order through ``DJMAIL_REAL_BACKEND``. When
    the transport cannot be reached they are all marked failed instead.
    """
    if not uuids:
        return 0
    connection = djmail_core._get_real_backend()
    error = open_connection(connection)
    if error:
        _fail(uuids, eligible, error)
        return 0
    try:
        return _for_each_claimed(
            uuids, eligible, lambda message: deliver_message(message, connection)
        )
    finally:
        close_connection(connection)


@shared_task
def send_queued_messages(message_uuids: list[str]) -> int:
    """Deliver messages queued by ``CeleryEmailBackend`` (only those still drafts)."""
    uuids = list(
        Message.objects.filter(uuid__in=message_uuids, status=Message.STATUS_DRAFT)
        .order_by("created_at")
        .values_list("uuid", flat=True)
    )
    return _deliver(uuids, Q(status=Message.STATUS_DRAFT))


def enqueue_messages(message_uuids: list[str]) -> None:
    """
    Queue ``send_queued_messages`` for ``message_uuids``. If the broker cannot take it, the
    messages still drafts are marked failed, so the retry task sends them later and the log
    shows why, rather than the error reaching the caller after its transaction committed.
    """
    try:
        send_queued_messages.delay(message_uuids)
    except Exception:
        logger.exception("Could not queue %s email(s) for delivery", len(message_uuids))
        _fail(list(message_uuids), Q(status=Message.STATUS_DRAFT), traceback.format_exc())


def _stale_drafts() -> list[str]:
    """
    Logged messages still drafts ``BASEAPP_EMAIL_LOG_STALE_DRAFT_MINUTES`` after they were
    written: their delivery was never attempted (the process died before queueing it, or
    the worker lost the task). Drafts without a row, left by plain djmail, are not touched.
    """
    minutes = getattr(settings, "BASEAPP_EMAIL_LOG_STALE_DRAFT_MINUTES", 30)
    if minutes is None:
        return []
    return list(
        Message.objects.filter(
            status=Message.STATUS_DRAFT,
            email_log__isnull=False,
            created_at__lt=timezone.now() - timedelta(minutes=minutes),
        )
        .order_by("created_at")
        .values_list("uuid", flat=True)
    )


@shared_task
def retry_failed_emails() -> int:
    """
    djmail's periodic pass, with transport errors counted as failures: discard failed
    messages past ``DJMAIL_MAX_RETRY_NUMBER``, then send the pending low-priority messages,
    the logged drafts whose delivery was never attempted, and the remaining failed ones,
    over one connection. Returns the number of messages sent.
    """
    max_retries = getattr(settings, "DJMAIL_MAX_RETRY_NUMBER", 3)
    discarded = djmail_core._mark_discarded_messages()

    # Collected before anything is attempted, so a message failing now is retried next run.
    pending = list(
        Message.objects.filter(status=Message.STATUS_PENDING)
        .order_by("-priority", "created_at")
        .values_list("uuid", flat=True)
    )
    failed = list(
        Message.objects.filter(status=Message.STATUS_FAILED, retry_count__lte=max_retries)
        .order_by("-priority", "created_at")
        .values_list("uuid", flat=True)
    )
    eligible = Q(status__in=[Message.STATUS_PENDING, Message.STATUS_DRAFT]) | Q(
        status=Message.STATUS_FAILED, retry_count__lte=max_retries
    )
    sent = _deliver(pending + _stale_drafts() + failed, eligible)

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
