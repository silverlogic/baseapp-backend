import short_url
from django.db import models
from django.urls import reverse
from model_utils.models import TimeStampedModel


class ShortUrl(TimeStampedModel):
    short_code = models.CharField(max_length=30, editable=False, unique=True, db_index=True)
    full_url = models.URLField()

    @property
    def short_url_path(self) -> str:
        return reverse("short_url_redirect_full_url", kwargs=dict(short_code=self.short_code))

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)
            self.short_code = short_url.encode_url(self.pk)
            self.save()
        else:
            super().save(*args, **kwargs)
