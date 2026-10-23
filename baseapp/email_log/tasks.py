import logging
import operator
import traceback
from datetime import timedelta
from functools import reduce
from typing import Callable, Iterable, Optional

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet, TextField
from django.db.models.functions import Cast
from django.utils import timezone
from djmail import core as djmail_core
from djmail.models import Message

from .attachments import delete_stored_attachments
from .models import get_email_log_model
from .services import close_connection, deliver_message, open_connection, record_failure
from .status import status_from_djmail

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


def valid_retention_days(days: object) -> bool:
    """A number of days a retention setting accepts: a non-negative integer."""
    return isinstance(days, int) and not isinstance(days, bool) and days >= 0


def _expired(older_than_days: Optional[int], by_category: dict[str, int]) -> Optional[Q]:
    """
    Rows past the general retention or their category's, or ``None`` when neither is set.
    A category whose days are ``None`` has no retention of its own; one with an invalid
    value is skipped (the ``baseapp_email_log.W002`` check reports it), so it cannot stop
    the purge of the others.
    """
    now = timezone.now()
    conditions = []
    if older_than_days is not None:
        conditions.append(Q(created__lt=now - timedelta(days=older_than_days)))
    for category, days in by_category.items():
        if days is None:
            continue
        if not valid_retention_days(days):
            logger.error(
                "Skipping the email log retention of %r: %r is not a number of days", category, days
            )
            continue
        conditions.append(Q(category=category, created__lt=now - timedelta(days=days)))
    return reduce(operator.or_, conditions) if conditions else None


def _holding_content(queryset: QuerySet) -> QuerySet:
    """
    Rows still holding content a scrub removes: a djmail message, a render context, a
    channel's text or a stored attachment (an entry with a ``path``).
    """
    return queryset.annotate(_attachments_text=Cast("attachments", TextField())).filter(
        Q(message__isnull=False)
        | ~Q(context={})
        | ~Q(delivery_body_text="")
        | Q(_attachments_text__contains='"path"')
    )


def _delete_rows(EmailLog: type, ids: list) -> int:
    deleted = 0
    for chunk in _chunks(ids):
        rows = list(EmailLog.objects.filter(pk__in=chunk).values("message_id", "attachments"))
        with transaction.atomic():
            _, per_model = EmailLog.objects.filter(pk__in=chunk).delete()
            deleted += per_model.get(EmailLog._meta.label, 0)
            message_ids = [row["message_id"] for row in rows if row["message_id"]]
            Message.objects.filter(uuid__in=message_ids).delete()
        for row in rows:
            delete_stored_attachments(row["attachments"])
    return deleted


def _summary(message: Optional[dict]) -> dict:
    """
    What a scrubbed email row keeps of its djmail message, in the row's own columns: the
    subject, sender, status and sent date. Nothing for rows without a message.
    """
    if message is None:
        return {}
    return {
        "delivery_subject": message["subject"] or "",
        "delivery_from_email": message["from_email"] or "",
        "delivery_status": status_from_djmail(message["status"]),
        "delivered_at": message["sent_at"],
    }


def _scrub_rows(EmailLog: type, ids: list) -> int:
    """
    Remove the content of rows kept for their idempotency key: their djmail message (the
    row's ``message`` becomes empty), stored attachments, render context and channel text.
    Who, what and when stay: the message's subject, sender, status and sent date are copied
    to the row first, and the key is kept. ``scrubbed_at`` marks the row.
    """
    scrubbed = 0
    for chunk in _chunks(ids):
        rows = list(EmailLog.objects.filter(pk__in=chunk).values("pk", "message_id", "attachments"))
        with transaction.atomic():
            message_ids = [row["message_id"] for row in rows if row["message_id"]]
            messages = {
                message["uuid"]: message
                for message in Message.objects.filter(uuid__in=message_ids).values(
                    "uuid", "subject", "from_email", "status", "sent_at"
                )
            }
            Message.objects.filter(uuid__in=message_ids).delete()
            now = timezone.now()
            for row in rows:
                EmailLog.objects.filter(pk=row["pk"]).update(
                    **_summary(messages.get(row["message_id"])),
                    context={},
                    delivery_body_text="",
                    attachments=[
                        {key: value for key, value in entry.items() if key != "path"}
                        for entry in row["attachments"] or []
                    ],
                    scrubbed_at=now,
                    modified=now,
                )
            scrubbed += len(rows)
        for row in rows:
            delete_stored_attachments(row["attachments"])
    return scrubbed


@shared_task
def purge_email_logs(
    older_than_days: Optional[int] = None, dry_run: bool = False
) -> dict[str, int]:
    """
    Delete log rows older than the retention, with their djmail messages and stored
    attachments, plus djmail messages that old with no row.

    The retention is ``older_than_days`` (default: ``BASEAPP_EMAIL_LOG_RETENTION_DAYS``),
    and, for the categories listed in ``BASEAPP_EMAIL_LOG_RETENTION_DAYS_BY_CATEGORY``,
    their own number of days, which applies whether or not the general retention is set.
    With neither set, nothing is purged.

    Rows with an idempotency key are scrubbed rather than deleted, so their keys keep
    blocking duplicate sends: their djmail message, stored attachments, context and channel
    text are removed. ``BASEAPP_EMAIL_LOG_PURGE_IDEMPOTENT`` deletes them instead.

    Returns the counts ``{"deleted", "scrubbed", "unlogged_messages"}``. With ``dry_run``
    nothing is changed and the counts are what would be purged.
    """
    if older_than_days is None:
        older_than_days = getattr(settings, "BASEAPP_EMAIL_LOG_RETENTION_DAYS", None)
    by_category = getattr(settings, "BASEAPP_EMAIL_LOG_RETENTION_DAYS_BY_CATEGORY", None) or {}
    if not isinstance(by_category, dict):
        logger.error("BASEAPP_EMAIL_LOG_RETENTION_DAYS_BY_CATEGORY is not a dict; ignoring it")
        by_category = {}
    counts = {"deleted": 0, "scrubbed": 0, "unlogged_messages": 0}
    expired = _expired(older_than_days, by_category)
    if expired is None:
        return counts

    EmailLog = get_email_log_model()
    logs = EmailLog.objects.filter(expired)
    to_scrub = EmailLog.objects.none()
    if not getattr(settings, "BASEAPP_EMAIL_LOG_PURGE_IDEMPOTENT", False):
        to_scrub = _holding_content(logs.filter(idempotency_key__isnull=False))
        logs = logs.filter(idempotency_key__isnull=True)
    unlogged = Message.objects.none()
    if older_than_days is not None:
        cutoff = timezone.now() - timedelta(days=older_than_days)
        unlogged = Message.objects.filter(created_at__lt=cutoff, email_log__isnull=True)

    if dry_run:
        counts.update(
            deleted=logs.count(), scrubbed=to_scrub.count(), unlogged_messages=unlogged.count()
        )
        return counts

    counts["deleted"] = _delete_rows(EmailLog, list(logs.values_list("pk", flat=True)))
    counts["scrubbed"] = _scrub_rows(EmailLog, list(to_scrub.values_list("pk", flat=True)))
    counts["unlogged_messages"], _ = unlogged.delete()
    logger.info(
        "Purged %(deleted)s email log rows, scrubbed %(scrubbed)s kept for their idempotency "
        "key, and purged %(unlogged_messages)s unlogged djmail messages",
        counts,
    )
    return counts
