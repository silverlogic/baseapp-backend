from django.db import models

from baseapp_cloudflare_stream_field import CloudflareStreamField
from baseapp_core.models import PublicIdMixin


# This model is only used for CloudflareStreamField tests.
# TO DO: Migrate to baseapp_cloudflare_stream_field.tests or remove it.
class Post(models.Model):
    title = models.CharField(max_length=100)
    video = CloudflareStreamField(null=True, blank=True, downloadable=False)


# This model is only used for PublicIdMixin tests.
class DummyPublicIdModel(PublicIdMixin, models.Model):
    name = models.CharField(max_length=100)
