import swapper
from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Count, IntegerField, OuterRef, Subquery, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql import RelayModel
from baseapp_core.models import (
    DocumentIdMixin,
    DocumentIdTargetMixin,
    DocumentIdUniqueTargetMixin,
)
from baseapp_core.plugins import apply_if_installed


def default_reactions_count():
    """Default value for `ReactableMetadata.reactions_count`. Returns a fresh dict
    keyed by `Reaction.ReactionTypes` enum names plus a `total` slot, all zero."""
    ReactionModel = swapper.load_model(
        "baseapp_reactions", "Reaction", required=False, require_ready=False
    )

    d = {"total": 0}
    if ReactionModel is not None:
        for reaction_type in ReactionModel.ReactionTypes:
            d[reaction_type.name] = 0

    return d


inheritances = []

if apps.is_installed("baseapp_profiles"):

    class ProfileMixin(models.Model):
        profile = models.ForeignKey(
            swapper.get_model_name("baseapp_profiles", "Profile"),
            verbose_name=_("profile"),
            related_name="reactions",
            on_delete=models.CASCADE,
            null=True,
            blank=True,
        )

        class Meta:
            abstract = True

    inheritances.append(ProfileMixin)


class AbstractReaction(
    *inheritances, DocumentIdTargetMixin, TimeStampedModel, DocumentIdMixin, RelayModel
):
    class ReactionTypes(models.IntegerChoices):
        LIKE = 1, _("like")
        DISLIKE = -1, _("dislike")

        @property
        def description(self):
            return self.label

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="reactions",
        on_delete=models.CASCADE,
    )

    reaction_type = models.IntegerField(choices=ReactionTypes.choices, default=ReactionTypes.LIKE)

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_reactions", "Reaction")
        unique_together = [
            apply_if_installed(
                "baseapp_profiles",
                ["profile", "target_document"],
                ["user", "target_document"],
            )
        ]

    def __str__(self):
        return "Reaction (%s) #%s by %s" % (
            self.reaction_type,
            self.id,
            self.user.first_name,
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.update_reactions_count(self.target)

    def delete(self, *args, **kwargs):
        target = self.target
        super().delete(*args, **kwargs)
        self.update_reactions_count(target)

    @classmethod
    def update_reactions_count(cls, target):
        """Recompute per-type reaction counts for `target` on its `ReactableMetadata` row."""
        if not target:
            return

        ReactionModel = swapper.load_model("baseapp_reactions", "Reaction")
        ReactableMetadata = swapper.load_model("baseapp_reactions", "ReactableMetadata")
        metadata = ReactableMetadata.get_or_create_for_object(target)
        if metadata is None:
            return

        # Single GROUP BY across all reactions for this target_document, then map
        # the integer reaction_type values back to enum names.
        rows = (
            ReactionModel.objects.filter(target_document_id=metadata.target_id)
            .values("reaction_type")
            .annotate(n=Count("id"))
        )
        counts = {rt.name: 0 for rt in ReactionModel.ReactionTypes}
        counts["total"] = 0
        for row in rows:
            name = ReactionModel.ReactionTypes(row["reaction_type"]).name
            counts[name] = row["n"]
            counts["total"] += row["n"]

        metadata.reactions_count = counts
        metadata.save(update_fields=["reactions_count", "modified"])

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import ReactionObjectType

        return ReactionObjectType


class AbstractReactableMetadata(DocumentIdUniqueTargetMixin, TimeStampedModel):
    """
    Stores reaction metadata (per-type counts dict + enabled flag) for any
    documentable object. Linked to `DocumentId` instead of adding columns to
    each reactable model, following the plugin architecture pattern.
    """

    reactions_count = models.JSONField(default=default_reactions_count, editable=False)
    is_reactions_enabled = models.BooleanField(default=True)

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_reactions", "ReactableMetadata")
        verbose_name = _("reactable metadata")
        verbose_name_plural = _("reactable metadata")

    def __str__(self):
        return f"ReactableMetadata for {self.target}"

    @classmethod
    def annotate_queryset(cls, queryset):
        """
        Annotate `queryset` with reactable metadata so resolvers don't N+1.
        Adds `_reactable_reactions_count`, `_reactable_is_reactions_enabled`,
        and a flat public `reactions_count_total` (integer cast of the
        `reactions_count->total` JSON key) so consumer-side ORDER BY can
        sort on a real expression. Mirrors the public-name pattern
        `CommentableMetadata.annotate_queryset` uses for `replies_count_total`.
        """
        model_cls = queryset.model
        ct_id = ContentType.objects.get_for_model(model_cls).pk
        metadata_qs = cls.objects.filter(
            target__content_type_id=ct_id,
            target__object_id=OuterRef("pk"),
        )
        total_subq = Subquery(
            metadata_qs.annotate(total=KeyTextTransform("total", "reactions_count")).values(
                "total"
            )[:1]
        )
        return queryset.annotate(
            _reactable_reactions_count=Subquery(metadata_qs.values("reactions_count")[:1]),
            _reactable_is_reactions_enabled=Coalesce(
                Subquery(
                    metadata_qs.values("is_reactions_enabled")[:1],
                    output_field=models.BooleanField(),
                ),
                Value(True),
            ),
            reactions_count_total=Coalesce(
                Cast(total_subq, output_field=IntegerField()),
                Value(0),
            ),
        )
