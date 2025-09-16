from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from .managers import BaseAPIKeyManager


class BaseAPIKey(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="%(class)s", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=256, null=False, blank=False)
    encrypted_api_key = models.BinaryField(null=False, blank=False, default=None)
    expiry_date = models.DateField(
        blank=True,
        null=True,
        verbose_name=_("Expiry Date"),
        help_text=_("The date the API Key expires."),
    )

    objects = BaseAPIKeyManager(api_key_prefix="BA")

    class Meta:
        abstract = True


class APIKey(BaseAPIKey):
    class Meta(BaseAPIKey.Meta):
        abstract = False
