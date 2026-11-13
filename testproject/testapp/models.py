from django.db import models
from django.utils.translation import gettext_lazy as _

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


# Used for testing baseapp_payments card holds: a target a hold can back. Its adapter is
# testproject.testapp.card_holds.HoldableOrderHoldTarget.
class HoldableOrder(DocumentIdMixin, models.Model):
    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        CANCELLED = "cancelled", _("Cancelled")
        CHARGED = "charged", _("Charged")

    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="holdable_orders")
    amount_cents = models.PositiveIntegerField(default=10_000)
    # None: the adapter's default buffer (Constance).
    buffer_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    charge_in_flight = models.BooleanField(default=False)
    target_date = models.DateField(null=True, blank=True)
