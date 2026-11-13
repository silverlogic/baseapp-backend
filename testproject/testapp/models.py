from django.db import models

from baseapp_cloudflare_stream_field import CloudflareStreamField
from baseapp_core.hashids.models import LegacyWithPkMixin
from baseapp_core.models import (
    DocumentIdMixin,
    DocumentIdTargetMixin,
    DocumentIdUniqueTargetMixin,
)


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


# Used for testing baseapp_core.models.DocumentIdUniqueTargetMixin.
class DummyUniqueDocumentTarget(DocumentIdUniqueTargetMixin, models.Model):
    counter = models.PositiveIntegerField(default=0)


# Used for testing baseapp_core.models.DocumentIdTargetMixin.
class DummyDocumentTarget(DocumentIdTargetMixin, models.Model):
    label = models.CharField(max_length=100, blank=True)


# Used for testing the public id REST helpers (fields, filters, queryset annotations).
class DummyPublicIdChildModel(DocumentIdMixin, models.Model):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        DummyPublicIdModel, on_delete=models.CASCADE, related_name="children"
    )
    previous = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="next_children"
    )
    legacy = models.ForeignKey(
        DummyLegacyModel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="public_id_children",
    )
    tags = models.ManyToManyField(DummyPublicIdModel, blank=True, related_name="tagged_children")
