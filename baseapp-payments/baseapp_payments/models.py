import swapper
from django.db import models
from django.utils.text import slugify

from . import webhook  # noqa


class BasePlan(models.Model):
    price = models.ForeignKey("djstripe.Price", on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    slug = models.SlugField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True

    def __str__(self):
        return f"Plan({self.pk}): {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def price_amount(self):
        if self.price_id:
            return self.price.unit_amount_decimal

    @property
    def interval(self):
        if self.price_id:
            return self.price.recurring.get("interval")


class Plan(BasePlan):
    class Meta:
        swappable = swapper.swappable_setting("baseapp_payments", "Plan")
