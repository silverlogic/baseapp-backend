import swapper
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql import RelayModel


class AbstractBaseRate(TimeStampedModel, RelayModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="ratings",
        on_delete=models.CASCADE,
    )
    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        verbose_name=_("profile"),
        related_name="ratings",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    target_content_type = models.ForeignKey(
        ContentType,
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    target_object_id = models.PositiveIntegerField(blank=True, null=True)
    target = GenericForeignKey("target_content_type", "target_object_id")
    value = models.IntegerField(default=0, blank=False, null=False)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["target_content_type", "target_object_id"]),
        ]

    def __str__(self):
        return "Rating (%s) by %s" % (
            self.id,
            self.user.first_name,
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        self.update_ratings_indicators()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)

        self.update_ratings_indicators()

    def update_ratings_indicators(self):
        target = self.target

        if not target:
            return

        RateModel = swapper.load_model("baseapp_ratings", "Rate")
        target_content_type = ContentType.objects.get_for_model(target)
        qs = RateModel.objects.filter(
            target_content_type=target_content_type,
            target_object_id=target.pk,
        )
        with transaction.atomic():
            target.ratings_count = qs.count()
            target.ratings_sum = qs.aggregate(models.Sum("value"))["value__sum"]
            target.ratings_average = (
                target.ratings_sum / target.ratings_count if target.ratings_count else 0
            )

            target.save(update_fields=["ratings_count", "ratings_sum", "ratings_average"])


class Rate(AbstractBaseRate):
    class Meta:
        unique_together = [["user", "target_content_type", "target_object_id"]]
        swappable = swapper.swappable_setting("baseapp_ratings", "Rate")

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import RatingObjectType

        return RatingObjectType


SwappedRating = swapper.load_model("baseapp_ratings", "Rate", required=False, require_ready=False)


class RatableModel(models.Model):
    ratings_count = models.IntegerField(default=0, editable=False)
    ratings_sum = models.IntegerField(default=0, editable=False)
    ratings_average = models.FloatField(default=0, editable=False)
    ratings = GenericRelation(
        SwappedRating,
        content_type_field="target_content_type",
        object_id_field="target_object_id",
    )
    is_ratings_enabled = models.BooleanField(default=True)

    class Meta:
        abstract = True
