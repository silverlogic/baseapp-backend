from typing import Any

import swapper
from constance import config
from django.apps import apps
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel


class BaseCustomer(TimeStampedModel):
    entity_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name=_("entity type"),
        # Abstract and swappable, so a literal name would clash between the
        # concrete Customer of any two apps that both subclass this.
        related_name="%(app_label)s_%(class)ss",
    )
    entity_id = models.PositiveIntegerField(_("entity id"))
    entity = GenericForeignKey("entity_type", "entity_id")
    remote_customer_id = models.CharField(_("remote customer id"), max_length=255)

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_payments", "Customer")
        verbose_name = _("customer")
        verbose_name_plural = _("customers")
        # One Customer per billed entity. Dropped incidentally by the invoice-endpoint
        # commit (#305); without it two concurrent requests for the same profile each
        # create a row, and each row gets its own Stripe customer.
        unique_together = ("entity_type", "entity_id")

    def __str__(self) -> str:
        return f"{self.entity} - {self.remote_customer_id}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not hasattr(self, "tracker"):
            raise RuntimeError(
                'BaseCustomer requires `tracker = FieldTracker(["entity"])`.'
                " Please ensure your concrete Customer model includes this tracker."
            )

        if not self.entity_type_id:
            try:
                # A dotted label, not a class. get_for_model reads model._meta, so
                # handing it the string raised AttributeError and this except turned
                # that into a config error - the fallback could never succeed.
                entity_model = apps.get_model(config.STRIPE_CUSTOMER_ENTITY_MODEL)
                self.entity_type = ContentType.objects.get_for_model(entity_model)
            except (LookupError, ValueError) as e:
                raise ValueError(f"Invalid STRIPE_CUSTOMER_ENTITY_MODEL configuration: {e}") from e

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
        verbose_name=_("customer"),
    )
    # Unique on its own rather than paired with the customer: the viewset resolves a
    # subscription with lookup_field="remote_subscription_id" and the webhook handler
    # filters on it alone, so a second row with the same id is MultipleObjectsReturned
    # on read and a multi-row delete on cancellation. A Stripe subscription id belongs
    # to exactly one customer anyway, which the old (customer, id) pair did not say.
    remote_subscription_id = models.CharField(
        _("remote subscription id"), max_length=255, unique=True
    )

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_payments", "Subscription")
        verbose_name = _("subscription")
        verbose_name_plural = _("subscriptions")


class PurchaseStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    PAID = "paid", _("Paid")
    FAILED = "failed", _("Failed")


class BasePurchase(TimeStampedModel):
    """A one-time charge for one or more products, made as one Stripe invoice.

    Never a subscription: it is charged once and is not renewed. The amounts are the
    ones Stripe charged at checkout, so a later price change does not rewrite them.
    Optional: projects that set ``BASEAPP_PAYMENTS_PURCHASE_MODEL`` (and the line model)
    get the purchase endpoints; without it the feature is off.
    """

    customer = models.ForeignKey(
        swapper.get_model_name("baseapp_payments", "Customer"),
        on_delete=models.PROTECT,
        related_name="purchases",
        verbose_name=_("customer"),
    )
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=PurchaseStatus.choices,
        default=PurchaseStatus.PENDING,
        db_index=True,
    )
    currency = models.CharField(_("currency"), max_length=3)
    # Minor units (cents), as Stripe reports them.
    subtotal = models.PositiveIntegerField(_("subtotal"))
    tax = models.PositiveIntegerField(_("tax"), default=0)
    total = models.PositiveIntegerField(_("total"))
    remote_invoice_id = models.CharField(
        _("remote invoice id"), max_length=255, unique=True, null=True, blank=True
    )
    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True)
    failed_at = models.DateTimeField(_("failed at"), null=True, blank=True)

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_payments", "Purchase")
        verbose_name = _("purchase")
        verbose_name_plural = _("purchases")
        ordering = ("-created",)

    def __str__(self) -> str:
        return f"{self.pk} - {self.status} - {self.total} {self.currency}"


class BasePurchaseLine(models.Model):
    purchase = models.ForeignKey(
        swapper.get_model_name("baseapp_payments", "Purchase"),
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("purchase"),
    )
    remote_product_id = models.CharField(_("remote product id"), max_length=255)
    remote_price_id = models.CharField(_("remote price id"), max_length=255)
    description = models.CharField(_("description"), max_length=255, blank=True)
    unit_amount = models.PositiveIntegerField(_("unit amount"))
    quantity = models.PositiveIntegerField(_("quantity"))
    amount = models.PositiveIntegerField(_("amount"))

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_payments", "PurchaseLine")
        verbose_name = _("purchase line")
        verbose_name_plural = _("purchase lines")
        ordering = ("pk",)

    def __str__(self) -> str:
        return f"{self.quantity} x {self.remote_price_id}"
