import swapper
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel


def default_reactions_count():
    ReactionModel = swapper.load_model("baseapp_reactions", "Reaction")

    d = {"total": 0}

    for reaction_type in ReactionModel.ReactionTypes:
        d[reaction_type.name] = 0

    return d


class AbstractBaseReaction(TimeStampedModel):
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

        update_reactions_count(self.target)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)

        update_reactions_count(self.target)


class Reaction(AbstractBaseReaction):
    class Meta:
        unique_together = [["user", "target_content_type", "target_object_id"]]
        swappable = swapper.swappable_setting("baseapp_reactions", "Reaction")


def update_reactions_count(target):
    counts = default_reactions_count()
    ReactionModel = swapper.load_model("baseapp_reactions", "Reaction")
    target_content_type = ContentType.objects.get_for_model(target)
    for reaction_type in ReactionModel.ReactionTypes:
        # TO DO: improve performance by removing the FOR and making 1 query to return counts for all types at once
        counts[reaction_type.name] = ReactionModel.objects.filter(
            target_content_type=target_content_type,
            target_object_id=target.pk,
            reaction_type=reaction_type,
        ).count()
        counts["total"] += counts[reaction_type.name]

    target.reactions_count = counts
    target.save(update_fields=["reactions_count"])


class ReactableModel(models.Model):
    reactions_count = models.JSONField(default=default_reactions_count)
    # can't load Reaction with swapper in this file
    # reactions = GenericRelation(
    #     lambda: swapper.load_model("baseapp_reactions", "Reaction", required=False), content_type_field="target_content_type", object_id_field="target_object_id"
    # )

    class Meta:
        abstract = True

    def get_my_permissions(self, request):
        raise NotImplementedError

    @property
    def reactions(self):
        ReactionModel = swapper.load_model("baseapp_reactions", "Reaction")
        target_content_type = ContentType.objects.get_for_model(self)
        return ReactionModel.objects.filter(
            target_content_type=target_content_type, target_object_id=self.pk
        )
