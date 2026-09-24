import swapper
from constance import config
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

    def __str__(self) -> str:
        return f"{self.entity} - {self.remote_customer_id}"

    def save(self, *args, **kwargs) -> None:
        if not hasattr(self, "tracker"):
            raise RuntimeError(
                'BaseCustomer requires `tracker = FieldTracker(["entity"])`.'
                " Please ensure your concrete Customer model includes this tracker."
            )

        if not self.entity_type_id:
            try:
                entity_model = config.STRIPE_CUSTOMER_ENTITY_MODEL
                self.entity_type = ContentType.objects.get_for_model(entity_model)
            except (AttributeError, ValueError, ContentType.DoesNotExist) as e:
                raise ValueError(f"Invalid STRIPE_CUSTOMER_ENTITY_MODEL configuration: {e}")

        if self.tracker.has_changed("entity") or not self.entity_id:
            if self.entity is not None:
                new_entity_type = ContentType.objects.get_for_model(self.entity)
                if new_entity_type != self.entity_type:
                    raise ValueError(
                        "Entity type is not the one configured in STRIPE_CUSTOMER_ENTITY_MODEL"
                    )
                self.entity_id = self.entity.id
            elif not self.entity_type:
                raise ValueError("Entity type must be set when entity is None")

        super().save(*args, **kwargs)


class BaseSubscription(TimeStampedModel):
    # A FK rather than master's remote_customer_id string: the subscription webhook
    # has to resolve the local Customer row, and matching on the Stripe id meant a
    # lookup that silently created orphans when it missed.
    customer = models.ForeignKey(
        swapper.get_model_name("baseapp_payments", "Customer"),
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    remote_subscription_id = models.CharField(max_length=255)

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_payments", "Subscription")
