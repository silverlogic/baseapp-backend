import swapper

from baseapp_core.graphql import RelayModel
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AbstractContentPost(
    RelayModel
):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("author"),
        related_name="content_posts",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    content = models.TextField()


    class Meta:
        abstract = True


class ContentPost(AbstractContentPost):
    class Meta(AbstractContentPost.Meta):
        abstract = False
        swappable = swapper.swappable_setting("baseapp_content_feed", "ContentPost")


SwappedContentPost = swapper.load_model(
    "baseapp_content_feed", "ContentPost", required=False, require_ready=False
)