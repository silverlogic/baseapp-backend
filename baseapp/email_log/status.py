"""
One string status for every log row, whatever its channel.

djmail stores an email's state as an integer on ``Message.status``; rows of other channels
(SMS, push, ...) store the string directly in ``delivery_status``. These helpers translate
between the two so consumers filter and display a single vocabulary.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from djmail.models import Message


class EmailLogStatus(models.TextChoices):
    QUEUED = "queued", _("Queued")
    SENDING = "sending", _("Sending")
    SENT = "sent", _("Sent")
    FAILED = "failed", _("Failed")
    DISCARDED = "discarded", _("Discarded")


_FROM_DJMAIL = {
    # A draft is a message djmail has stored but not delivered yet: the sync backend is
    # about to hand it to the transport, or the Celery backend has queued it.
    Message.STATUS_DRAFT: EmailLogStatus.QUEUED,
    # Low-priority messages wait for the periodic task.
    Message.STATUS_PENDING: EmailLogStatus.QUEUED,
    Message.STATUS_SENT: EmailLogStatus.SENT,
    Message.STATUS_FAILED: EmailLogStatus.FAILED,
    Message.STATUS_DISCARDED: EmailLogStatus.DISCARDED,
}

_TO_DJMAIL = {
    EmailLogStatus.QUEUED: Message.STATUS_DRAFT,
    # djmail has no in-flight state; a message being sent is still a draft.
    EmailLogStatus.SENDING: Message.STATUS_DRAFT,
    EmailLogStatus.SENT: Message.STATUS_SENT,
    EmailLogStatus.FAILED: Message.STATUS_FAILED,
    EmailLogStatus.DISCARDED: Message.STATUS_DISCARDED,
}


def status_from_djmail(djmail_status: int) -> str:
    """The string status of a djmail ``Message.status`` value."""
    try:
        return _FROM_DJMAIL[djmail_status].value
    except KeyError:
        raise ValueError(f"Unknown djmail status: {djmail_status!r}") from None


def status_to_djmail(status: str) -> int:
    """The djmail ``Message.status`` value that stores ``status``."""
    return _TO_DJMAIL[EmailLogStatus(status)]


def djmail_statuses_for(status: str) -> list[int]:
    """Every djmail status that reads as ``status``, for filtering (``queued`` is two)."""
    status = EmailLogStatus(status)
    return [djmail_status for djmail_status, value in _FROM_DJMAIL.items() if value == status]
