import swapper
from baseapp_core.graphql import RelayModel
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.models import random_name_in

class AbstractContentPost(RelayModel, TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        related_name="content_posts",
        on_delete=models.CASCADE,
    )
    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        verbose_name=_("profile"),
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



class AbstractContentPostImage(RelayModel):
    image = models.ImageField(
        _("image"), upload_to=random_name_in("content_feed_images"), blank=True, null=True
    )
    post = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("post"),
        related_name="content_post",
        on_delete=models.CASCADE,
    )

    class Meta:
        abstract = True

class ContentPostImage(AbstractContentPostImage):

    
    class Meta(AbstractContentPostImage.Meta):
        abstract = False
        swappable = swapper.swappable_setting("baseapp_content_feed", "ContentPostImage")
