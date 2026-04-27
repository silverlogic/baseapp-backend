import swapper
from django.db import models
from django.utils.translation import gettext_lazy as _


class MentionableModel(models.Model):
    """Abstract mixin that adds a `mentioned_profiles` M2M to any model.

    The related_name template (`%(app_label)s_%(class)s_mentions`) keeps each
    consuming model's reverse accessor distinct on Profile, e.g.
    `profile.baseapp_comments_comment_mentions` and
    `profile.baseapp_chats_message_mentions`.

    Notification dispatch (signals, celery tasks, verbs) stays per-model — only
    the field shape is shared here.
    """

    mentioned_profiles = models.ManyToManyField(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        verbose_name=_("mentioned profiles"),
        related_name="%(app_label)s_%(class)s_mentions",
        blank=True,
    )

    class Meta:
        abstract = True
