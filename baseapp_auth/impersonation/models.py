from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from baseapp_core.graphql.models import RelayModel


class ImpersonationSessionQuerySet(models.QuerySet):
    def active(self) -> "ImpersonationSessionQuerySet":
        """Sessions not ended and not yet past their expiry."""
        return self.filter(ended_at__isnull=True, expires_at__gt=timezone.now())


class ImpersonationSession(RelayModel):
    """One period in which `impersonator` acts as `target`, with the reason they gave."""

    class EndReason(models.TextChoices):
        ENDED = "ended", _("Ended by the impersonator")
        EXPIRED = "expired", _("Expired")
        REVOKED = "revoked", _("Revoked")

    impersonator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="started_impersonation_sessions",
        on_delete=models.CASCADE,
        verbose_name=_("impersonator"),
    )
    target = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="impersonation_sessions",
        on_delete=models.CASCADE,
        verbose_name=_("target"),
    )
    reason = models.TextField(_("reason"))
    read_only = models.BooleanField(
        _("read only"),
        default=True,
        help_text=_("Whether writes were refused during this session."),
    )
    started_at = models.DateTimeField(_("started at"), default=timezone.now)
    expires_at = models.DateTimeField(_("expires at"))
    ended_at = models.DateTimeField(_("ended at"), null=True, blank=True)
    end_reason = models.CharField(
        _("end reason"), max_length=16, choices=EndReason.choices, blank=True
    )
    ip = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.TextField(_("user agent"), blank=True)

    objects = ImpersonationSessionQuerySet.as_manager()

    class Meta:
        ordering = ["-started_at"]
        verbose_name = _("impersonation session")
        verbose_name_plural = _("impersonation sessions")
        indexes = [
            models.Index(
                fields=["expires_at"],
                condition=Q(ended_at__isnull=True),
                name="baseapp_imp_session_open_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.impersonator_id} as {self.target_id} ({self.started_at:%Y-%m-%d %H:%M})"

    @property
    def is_active(self) -> bool:
        return self.ended_at is None and self.expires_at > timezone.now()


class ImpersonationAction(models.Model):
    """A write made during an impersonation session: a REST request or a GraphQL mutation."""

    session = models.ForeignKey(
        ImpersonationSession,
        related_name="actions",
        on_delete=models.CASCADE,
        verbose_name=_("session"),
    )
    created = models.DateTimeField(_("created"), default=timezone.now)
    method = models.CharField(_("method"), max_length=10)
    path = models.TextField(_("path"))
    operation_name = models.CharField(
        _("operation name"),
        max_length=255,
        blank=True,
        help_text=_("The GraphQL mutation, when the write was one."),
    )
    status_code = models.PositiveSmallIntegerField(
        _("status code"),
        null=True,
        blank=True,
        help_text=_("The HTTP status of a REST write. Empty for GraphQL mutations."),
    )

    class Meta:
        ordering = ["created"]
        verbose_name = _("impersonation action")
        verbose_name_plural = _("impersonation actions")

    def __str__(self) -> str:
        return f"{self.method} {self.operation_name or self.path}"
