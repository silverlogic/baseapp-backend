import swapper
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql.models import RelayModel
from baseapp_core.models import DocumentId


class AbstractBaseMention(TimeStampedModel, RelayModel):
    """A profile mentioned inside a target document.

    `target` is a `DocumentId` so any model registered with the DocumentId
    registry can be a mention target without adding fields or migrations of
    its own — mirrors the `baseapp_follows.Follow` pattern.
    """

    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        verbose_name=_("profile"),
        related_name="mentions_received",
        on_delete=models.CASCADE,
    )
    target = models.ForeignKey(
        DocumentId,
        verbose_name=_("target"),
        related_name="mentions",
        on_delete=models.CASCADE,
    )

    class Meta:
        abstract = True
        unique_together = [("profile", "target")]
        indexes = [models.Index(fields=["target", "profile"])]

    def __str__(self):
        return "{} mentioned in {}".format(self.profile, self.target)

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import MentionObjectType

        return MentionObjectType


class Mention(AbstractBaseMention):
    class Meta(AbstractBaseMention.Meta):
        swappable = swapper.swappable_setting("baseapp_mentions", "Mention")
