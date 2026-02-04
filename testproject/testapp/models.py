from django.db import models

from baseapp_cloudflare_stream_field import CloudflareStreamField
from baseapp_core.hashids.models import LegacyWithPkMixin
from baseapp_core.models import DocumentIdMixin


# This model is only used for CloudflareStreamField tests.
# TO DO: Migrate to baseapp_cloudflare_stream_field.tests or remove it.
class Post(models.Model):
    title = models.CharField(max_length=100)
    video = CloudflareStreamField(null=True, blank=True, downloadable=False)


# ==============================
# The following models are used for testing baseapp_core.hashids features.
# ==============================
class DummyPublicIdModel(DocumentIdMixin, models.Model):
    name = models.CharField(max_length=100)


class DummyLegacyWithPkModel(LegacyWithPkMixin, models.Model):
    name = models.CharField(max_length=100)


class DummyLegacyModel(models.Model):
    name = models.CharField(max_length=100)
