from django.db import models

from baseapp_cloudflare_stream_field import CloudflareStreamField


# This model is only used for CloudflareStreamField tests.
# TO DO: Migrate to baseapp_cloudflare_stream_field.tests or remove it.
class Post(models.Model):
    title = models.CharField(max_length=100)
    video = CloudflareStreamField(null=True, blank=True, downloadable=False)
