import short_url
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel


class ShortUrl(TimeStampedModel):
    short_code = models.CharField(
        _("short code"), max_length=30, editable=False, unique=True, db_index=True
    )
    full_url = models.URLField(_("full URL"), max_length=2000)

    class Meta:
        verbose_name = _("short URL")
        verbose_name_plural = _("short URLs")

    @property
    def short_url_path(self) -> str:
        return reverse("v1:short_url_redirect_full_url", kwargs={"short_code": self.short_code})

    @property
    def public_short_url(self) -> str:
        return self.short_url_path.replace("/v1/", "/")

    def save(self, *args, **kwargs) -> None:
        creating = not self.pk
        super().save(*args, **kwargs)
        if creating:
            self.short_code = short_url.encode_url(self.pk)
            super().save(update_fields=["short_code"])
