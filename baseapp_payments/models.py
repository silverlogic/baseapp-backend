import swapper
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from model_utils.models import TimeStampedModel


class BaseCustomer(TimeStampedModel):
    entity_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    entity_id = models.PositiveIntegerField()
    entity = GenericForeignKey("entity_type", "entity_id")
    remote_customer_id = models.CharField(max_length=255)

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_payments", "Customer")
        unique_together = ("entity_type", "entity_id")

    def __str__(self):
        return f"{self.entity} - {self.remote_customer_id}"

    def save(self, *args, **kwargs):
        if not hasattr(self, "tracker"):
            raise RuntimeError(
                'BaseCustomer requires `tracker = FieldTracker(["entity"])`.'
                " Please ensure your concrete Customer model includes this tracker."
            )

        if self.tracker.has_changed("entity") and self.entity:
            self.entity_type = ContentType.objects.get_for_model(self.entity)
            self.entity_id = self.entity.id
        super().save(*args, **kwargs)


class BaseSubscription(TimeStampedModel):
    remote_customer_id = models.CharField(max_length=255)
    remote_subscription_id = models.CharField(max_length=255)

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_payments", "Subscription")
        unique_together = ("remote_customer_id", "remote_subscription_id")
