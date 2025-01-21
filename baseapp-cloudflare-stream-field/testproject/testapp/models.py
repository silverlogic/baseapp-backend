from django.db import models

from baseapp_cloudflare_stream_field import CloudflareStreamField


class Post(models.Model):
    title = models.CharField(max_length=100)
    video = CloudflareStreamField(null=True, blank=True, downloadable=False)
