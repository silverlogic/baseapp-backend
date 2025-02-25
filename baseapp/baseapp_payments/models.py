import swapper
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class BaseCustomer(models.Model):
    entity_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    entity_id = models.PositiveIntegerField()
    entity = GenericForeignKey("entity_type", "entity_id")
    remote_customer_id = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.entity} - {self.remote_customer_id}"

    class Meta:
        abstract = True


class BaseSubscription(models.Model):
    remote_customer_id = models.CharField(max_length=255)
    remote_subscription_id = models.CharField(max_length=255)

    class Meta:
        abstract = True


class Customer(BaseCustomer):
    class Meta:
        swappable = swapper.swappable_setting("baseapp_payments", "Customer")
        unique_together = ("entity_type", "entity_id")


class Subscription(BaseSubscription):
    class Meta:
        swappable = swapper.swappable_setting("baseapp_payments", "Subscription")
        unique_together = ("remote_customer_id", "remote_subscription_id")
