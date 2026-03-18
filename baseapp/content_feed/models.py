import swapper
from django.apps import apps
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql import RelayModel
from baseapp_core.models import DocumentIdMixin, random_name_in
from baseapp_reactions.models import ReactableModel

inheritances = []

if apps.is_installed("baseapp_profiles"):

    class ProfileMixin(models.Model):
        profile = models.ForeignKey(
            swapper.get_model_name("baseapp_profiles", "Profile"),
            verbose_name=_("profile"),
            related_name="content_posts",
            on_delete=models.SET_NULL,
            null=True,
            blank=True,
        )

        class Meta:
            abstract = True

    inheritances.append(ProfileMixin)


class AbstractContentPost(
    *inheritances, DocumentIdMixin, RelayModel, TimeStampedModel, ReactableModel
):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        related_name="content_posts",
        on_delete=models.CASCADE,
    )
    content = models.TextField()

    class Meta:
        abstract = True

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import ContentPostObjectType

        return ContentPostObjectType


class ContentPost(AbstractContentPost):
    class Meta(AbstractContentPost.Meta):
        abstract = False
        swappable = swapper.swappable_setting("baseapp_content_feed", "ContentPost")


class AbstractContentPostImage(DocumentIdMixin, RelayModel):
    image = models.ImageField(
        _("image"), upload_to=random_name_in("content_feed_images"), blank=True, null=True
    )
    post = models.ForeignKey(
        swapper.get_model_name("baseapp_content_feed", "ContentPost"),
        verbose_name=_("post"),
        related_name="images",
        on_delete=models.CASCADE,
    )

    class Meta:
        abstract = True

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import ContentPostImageObjectType

        return ContentPostImageObjectType


class ContentPostImage(AbstractContentPostImage):
    class Meta(AbstractContentPostImage.Meta):
        abstract = False
        swappable = swapper.swappable_setting("baseapp_content_feed", "ContentPostImage")
