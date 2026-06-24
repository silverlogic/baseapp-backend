import swapper
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql.models import RelayModel
from baseapp_core.models import DocumentIdMixin, DocumentIdTargetMixin


class AbstractBaseMention(TimeStampedModel, DocumentIdTargetMixin, DocumentIdMixin, RelayModel):
    """A profile mentioned inside a target document.

    The mention target is a `DocumentId`, provided by
    `DocumentIdTargetMixin.target_document`, so any model registered with the
    DocumentId registry can be a mention target without adding fields or
    migrations of its own — mirrors the `baseapp_reactions.Reaction` pattern.
    """

    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        verbose_name=_("profile"),
        related_name="mentions_received",
        on_delete=models.CASCADE,
    )

    class Meta:
        abstract = True
        unique_together = [("profile", "target_document")]
        swappable = swapper.swappable_setting("baseapp_mentions", "Mention")

    def __str__(self):
        return "{} mentioned in {}".format(self.profile, self.target_document)

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import MentionObjectType

        return MentionObjectType
