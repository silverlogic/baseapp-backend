import swapper
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class BaseUserReferral(models.Model):
    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("referrer"),
        related_name="referrals",
        on_delete=models.CASCADE,
    )
    referee = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name=_("referee"),
        related_name="referred_by",
        on_delete=models.CASCADE,
    )

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_referrals", "UserReferral")
        verbose_name = _("user referral")
        verbose_name_plural = _("user referrals")
