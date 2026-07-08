import swapper
from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.db.models import OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql import RelayModel
from baseapp_core.models import (
    DocumentIdMixin,
    DocumentIdTargetMixin,
    DocumentIdUniqueTargetMixin,
)

inheritances = []

if apps.is_installed("baseapp_profiles"):

    class ProfileMixin(models.Model):
        profile = models.ForeignKey(
            swapper.get_model_name("baseapp_profiles", "Profile"),
            verbose_name=_("profile"),
            related_name="ratings",
            on_delete=models.CASCADE,
            null=True,
            blank=True,
        )

        class Meta:
            abstract = True

    inheritances.append(ProfileMixin)


class AbstractRate(
    *inheritances, DocumentIdTargetMixin, TimeStampedModel, DocumentIdMixin, RelayModel
):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="ratings",
        on_delete=models.CASCADE,
    )

    value = models.IntegerField(default=0, blank=False, null=False)

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_ratings", "Rate")
        unique_together = [["user", "target_document"]]

    def __str__(self):
        return "Rating (%s) by %s" % (
            self.id,
            self.user.first_name,
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.update_ratings_indicators(self.target)

    def delete(self, *args, **kwargs):
        target = self.target
        super().delete(*args, **kwargs)
        self.update_ratings_indicators(target)

    @classmethod
    def update_ratings_indicators(cls, target):
        """Recompute count/sum/average on `RatableMetadata` for `target`."""
        if not target:
            return

        RatableMetadata = swapper.load_model("baseapp_ratings", "RatableMetadata")
        metadata = RatableMetadata.get_or_create_for_object(target)
        if metadata is None:
            return

        agg = cls.objects.filter(target_document=metadata.target_id).aggregate(
            n=models.Count("id"),
            s=Sum("value"),
        )
        count = agg["n"] or 0
        total = agg["s"] or 0

        with transaction.atomic():
            metadata.ratings_count = count
            metadata.ratings_sum = total
            metadata.ratings_average = (total / count) if count else 0
            metadata.save(
                update_fields=["ratings_count", "ratings_sum", "ratings_average", "modified"]
            )

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import RatingObjectType

        return RatingObjectType


class AbstractRatableMetadata(DocumentIdUniqueTargetMixin, TimeStampedModel):
    """
    Stores rating metadata (count / sum / average / enabled flag) for any
    documentable object. Linked to `DocumentId` instead of adding columns to each
    ratable model, following the plugin architecture pattern.
    """

    ratings_count = models.IntegerField(default=0, editable=False)
    ratings_sum = models.IntegerField(default=0, editable=False)
    ratings_average = models.FloatField(default=0, editable=False)
    is_ratings_enabled = models.BooleanField(default=True)

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_ratings", "RatableMetadata")
        verbose_name = _("ratable metadata")
        verbose_name_plural = _("ratable metadata")

    def __str__(self):
        return f"RatableMetadata for {self.target}"

    @classmethod
    def annotate_queryset(cls, queryset):
        """
        Annotate `queryset` with ratable metadata so resolvers don't N+1.
        Adds `_ratable_ratings_count`, `_ratable_ratings_sum`,
        `_ratable_ratings_average`, `_ratable_is_ratings_enabled`.
        """
        model_cls = queryset.model
        ct_id = ContentType.objects.get_for_model(model_cls).pk
        metadata_qs = cls.objects.filter(
            target__content_type_id=ct_id,
            target__object_id=OuterRef("pk"),
        )
        return queryset.annotate(
            _ratable_ratings_count=Coalesce(
                Subquery(metadata_qs.values("ratings_count")[:1]),
                Value(0),
            ),
            _ratable_ratings_sum=Coalesce(
                Subquery(metadata_qs.values("ratings_sum")[:1]),
                Value(0),
            ),
            _ratable_ratings_average=Coalesce(
                Subquery(metadata_qs.values("ratings_average")[:1]),
                Value(0.0),
            ),
            _ratable_is_ratings_enabled=Coalesce(
                Subquery(
                    metadata_qs.values("is_ratings_enabled")[:1],
                    output_field=models.BooleanField(),
                ),
                Value(True),
            ),
        )
