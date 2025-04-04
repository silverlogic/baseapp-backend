import swapper
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Count
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql import RelayModel


def default_reactions_count():
    ReactionModel = swapper.load_model("baseapp_reactions", "Reaction")

    d = {"total": 0}

    for reaction_type in ReactionModel.ReactionTypes:
        d[reaction_type.name] = 0

    return d


class AbstractBaseReaction(TimeStampedModel, RelayModel):
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

    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        verbose_name=_("profile"),
        related_name="reactions",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    reaction_type = models.IntegerField(choices=ReactionTypes.choices, default=ReactionTypes.LIKE)

    target_content_type = models.ForeignKey(
        ContentType,
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        db_index=True,
    )
    target_object_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    target = GenericForeignKey("target_content_type", "target_object_id")

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["target_content_type", "target_object_id"]),
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
        super().delete(*args, **kwargs)

        self.update_reactions_count(self.target)

    def update_reactions_count(self, target):
        if not target:
            return

        ReactionModel = swapper.load_model("baseapp_reactions", "Reaction")
        target_content_type = ContentType.objects.get_for_model(target)

        # Annotate and group by reaction_type
        reaction_counts = (
            ReactionModel.objects.filter(
                target_content_type=target_content_type, target_object_id=target.pk
            )
            .values("reaction_type")
            .annotate(count=Count("id"))
        )

        # Initialize the counts dictionary
        counts = {str(reaction_type.name): 0 for reaction_type in ReactionModel.ReactionTypes}
        counts["total"] = 0

        # Update the counts dictionary with the results from the query
        for reaction_count in reaction_counts:
            reaction_type_value = reaction_count["reaction_type"]
            reaction_type_name = ReactionModel.ReactionTypes(reaction_type_value).name
            counts[reaction_type_name] = reaction_count["count"]
            counts["total"] += reaction_count["count"]

        # Assuming `target` has a `reactions_count` field of type JSONField or similar
        target.reactions_count = counts
        target.save(update_fields=["reactions_count"])


class Reaction(AbstractBaseReaction):
    class Meta:
        unique_together = [["user", "target_content_type", "target_object_id"]]
        swappable = swapper.swappable_setting("baseapp_reactions", "Reaction")

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import ReactionObjectType

        return ReactionObjectType


SwappedReaction = swapper.load_model(
    "baseapp_reactions", "Reaction", required=False, require_ready=False
)


class ReactableModel(models.Model):
    reactions_count = models.JSONField(default=default_reactions_count, editable=False)
    reactions = GenericRelation(
        SwappedReaction,
        content_type_field="target_content_type",
        object_id_field="target_object_id",
    )
    is_reactions_enabled = models.BooleanField(default=True)

    class Meta:
        abstract = True
