from datetime import datetime
from typing import Optional

import swapper
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from .status import EmailLogStatus, djmail_statuses_for, status_from_djmail


class EmailLogQuerySet(models.QuerySet):
    def with_status(self, status: str) -> "EmailLogQuerySet":
        """
        Rows whose unified ``status`` is ``status``: email rows by their djmail message,
        other channels by their own ``delivery_status``.
        """
        return self.filter(
            Q(message__status__in=djmail_statuses_for(status))
            | Q(message__isnull=True, delivery_status=status)
        )

    def for_object(self, obj: models.Model) -> "EmailLogQuerySet":
        """Rows whose related object is ``obj``."""
        return self.filter(
            related_content_type=ContentType.objects.get_for_model(obj),
            related_object_id=str(obj.pk),
        )


class AbstractEmailLog(TimeStampedModel):
    """
    What djmail does not store about a message.

    djmail's ``Message`` is the one store of every email: subject, bodies, from/to, status,
    exception, sent_at, and the pickled message used for retries. A log row is linked
    one-to-one to it and adds the metadata djmail lacks: cc/bcc/reply-to, the full
    recipient list, the template and render context (to re-render on resend), attachments
    kept in storage, the related object, who sent it, what it re-sends, and an idempotency
    key.

    Messages of other channels (SMS, push, ...) never go through djmail: their rows have no
    ``message`` and carry their own text and delivery state in the ``delivery_*`` columns.

    Read a row through the properties (``subject``, ``body_text``, ``to``, ``status``,
    ``sent_at``, ``error``, ...), which resolve from djmail for email rows and from the
    row's own columns otherwise.
    """

    class Channel(models.TextChoices):
        EMAIL = "email", _("Email")
        SMS = "sms", _("SMS")
        OTHER = "other", _("Other")

    Status = EmailLogStatus

    # SET_NULL, not PROTECT: djmail's own cleanup (`djmail_delete_old_messages`) and its
    # admin must keep deleting messages. The row then survives as metadata only, so an
    # idempotency key keeps blocking a second send after the message itself is gone.
    message = models.OneToOneField(
        "djmail.Message",
        verbose_name=_("message"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="email_log",
    )
    channel = models.CharField(
        _("channel"), max_length=20, choices=Channel.choices, default=Channel.EMAIL
    )

    recipients = models.JSONField(_("recipients"), default=list, blank=True)
    cc = models.JSONField(_("cc"), default=list, blank=True)
    bcc = models.JSONField(_("bcc"), default=list, blank=True)
    reply_to = models.JSONField(_("reply to"), default=list, blank=True)

    template = models.CharField(_("template"), max_length=255, blank=True)
    context = models.JSONField(
        _("context"),
        default=dict,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text=_("Render context, kept to re-render the message on resend."),
    )
    attachments = models.JSONField(
        _("attachments"),
        default=list,
        blank=True,
        help_text=_("Name, content type and size of each attachment, and its storage path."),
    )

    related_content_type = models.ForeignKey(
        ContentType,
        verbose_name=_("related content type"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    # A CharField so objects with UUID or string primary keys can be related too.
    related_object_id = models.CharField(_("related object id"), max_length=255, blank=True)
    related_object = GenericForeignKey("related_content_type", "related_object_id")
    related_label = models.CharField(_("related label"), max_length=255, blank=True)

    category = models.CharField(_("category"), max_length=100, blank=True, db_index=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("sent by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_email_logs",
    )
    # The swappable name rather than "self": a swapped-out default would otherwise point at
    # itself while its migration points at the setting, and every project that swaps the
    # model would get a phantom migration for this package.
    resend_of = models.ForeignKey(
        swapper.get_model_name("baseapp_email_log", "EmailLog"),
        verbose_name=_("resend of"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resends",
    )
    idempotency_key = models.CharField(
        _("idempotency key"), max_length=255, null=True, blank=True, unique=True
    )

    # Other channels only: an email row reads these from its djmail message.
    delivery_to = models.CharField(_("delivery to"), max_length=255, blank=True)
    delivery_body_text = models.TextField(_("delivery body text"), blank=True)
    delivery_status = models.CharField(
        _("delivery status"), max_length=20, choices=EmailLogStatus.choices, blank=True
    )
    delivered_at = models.DateTimeField(_("delivered at"), null=True, blank=True)
    delivery_error = models.TextField(_("delivery error"), blank=True)

    objects = EmailLogQuerySet.as_manager()

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_email_log", "EmailLog")
        ordering = ["-created"]
        verbose_name = _("email log")
        verbose_name_plural = _("email logs")
        indexes = [
            models.Index(fields=["related_content_type", "related_object_id"]),
            models.Index(fields=["created"]),
        ]

    def __str__(self) -> str:
        to = self.to or ",".join([*self.cc, *self.bcc]) or "-"
        return f"{self.get_channel_display()} to {to}: {self.subject or '-'}"

    @property
    def subject(self) -> str:
        return self.message.subject if self.message_id else ""

    @property
    def body_text(self) -> str:
        return self.message.body_text if self.message_id else self.delivery_body_text

    @property
    def body_html(self) -> str:
        return self.message.body_html if self.message_id else ""

    @property
    def from_email(self) -> str:
        return self.message.from_email if self.message_id else ""

    @property
    def to(self) -> str:
        """
        The To addresses comma separated, as djmail stores them (from the row's own list once
        the djmail message is gone), or the channel's address for other channels.
        """
        if self.channel != self.Channel.EMAIL:
            return self.delivery_to
        return (self.message.to_email if self.message_id else "") or ",".join(self.recipients)

    @property
    def status(self) -> Optional[str]:
        """
        ``queued``, ``sending``, ``sent``, ``failed`` or ``discarded``. ``None`` for an email
        row whose djmail message has been deleted.
        """
        if self.message_id:
            return status_from_djmail(self.message.status)
        return self.delivery_status or None

    @property
    def sent_at(self) -> Optional[datetime]:
        return self.message.sent_at if self.message_id else self.delivered_at

    @property
    def error(self) -> str:
        """The transport error djmail recorded (its traceback), or the channel's error."""
        return self.message.exception if self.message_id else self.delivery_error

    def mark_delivery(self, status: str, *, error: str = "") -> None:
        """Record the delivery state of a row of another channel (it has no djmail message)."""
        if self.channel == self.Channel.EMAIL:
            raise ValueError("An email row's status lives on its djmail message.")
        self.delivery_status = EmailLogStatus(status).value
        self.delivery_error = error
        if self.delivery_status == EmailLogStatus.SENT:
            self.delivered_at = timezone.now()
        self.save(update_fields=["delivery_status", "delivery_error", "delivered_at", "modified"])


class EmailLog(AbstractEmailLog):
    """
    The default concrete log, so the package works without a project model. Projects that
    need more columns subclass ``AbstractEmailLog`` and point
    ``BASEAPP_EMAIL_LOG_EMAILLOG_MODEL`` at their model.
    """

    class Meta(AbstractEmailLog.Meta):
        swappable = swapper.swappable_setting("baseapp_email_log", "EmailLog")


def get_email_log_model() -> type[AbstractEmailLog]:
    """The active (possibly swapped) email log model."""
    return swapper.load_model("baseapp_email_log", "EmailLog")
