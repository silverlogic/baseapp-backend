import pgtrigger
import swapper
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql import RelayModel
from baseapp_reactions.models import ReactableModel
from baseapp_reports.models import ReportableModel

from .validators import blocked_words_validator


def default_comments_count():
    return {
        "total": 0,
        "main": 0,
        "replies": 0,
        "pinned": 0,
        "reported": 0,
    }


class AbstractCommentableModel(models.Model):
    comments_count = models.JSONField(
        default=default_comments_count, verbose_name=_("comments count"), editable=False
    )
    is_comments_enabled = models.BooleanField(default=True, verbose_name=_("is comments enabled"))

    class Meta:
        abstract = True


class CommentStatus(models.IntegerChoices):
    DELETED = 0, _("deleted")
    PUBLISHED = 1, _("published")


class NonDeletedComments(models.Manager):
    """Automatically filters out soft deleted objects from QuerySets"""

    def get_queryset(self):
        return super(NonDeletedComments, self).get_queryset().exclude(status=CommentStatus.DELETED)


class AbstractComment(
    TimeStampedModel, AbstractCommentableModel, ReactableModel, ReportableModel, RelayModel
):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        related_name="comments",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    profile = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        verbose_name=_("profile"),
        related_name="comments",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    body = models.TextField(
        blank=True, null=True, validators=[blocked_words_validator], verbose_name=_("body")
    )

    language = models.CharField(
        _("language"),
        max_length=10,
        null=True,
        blank=True,
        help_text=_("languaged used in the comment"),
    )

    is_edited = models.BooleanField(default=False, verbose_name=_("is edited"))
    is_pinned = models.BooleanField(default=False, verbose_name=_("is pinned"))

    target_content_type = models.ForeignKey(
        ContentType,
        verbose_name=_("target content type"),
        blank=True,
        null=True,
        related_name="comments_inbox",
        on_delete=models.CASCADE,
        db_index=True,
    )
    target_object_id = models.PositiveIntegerField(
        blank=True, null=True, db_index=True, verbose_name=_("target object id")
    )
    target = GenericForeignKey("target_content_type", "target_object_id")
    target.short_description = _("target")  # because GenericForeignKey doens't have verbose_name

    in_reply_to = models.ForeignKey(
        to=swapper.get_model_name("baseapp_comments", "Comment"),
        verbose_name=_("in reply to"),
        blank=True,
        null=True,
        related_name="comments",
        on_delete=models.CASCADE,
    )

    status = models.IntegerField(
        _("status"), choices=CommentStatus.choices, default=CommentStatus.PUBLISHED, db_index=True
    )

    objects = models.Manager()
    objects_visible = NonDeletedComments()

    class Meta:
        abstract = True
        ordering = ["-is_pinned", "-created"]
        indexes = [
            models.Index(
                fields=[
                    "target_content_type",
                    "target_object_id",
                    "status",
                    "-is_pinned",
                    "-created",
                ]
            ),
        ]
        triggers = [
            pgtrigger.SoftDelete(name="soft_delete", field="status", value=CommentStatus.DELETED)
        ]
        permissions = [
            ("pin_comment", _("can pin comments")),
            ("report_comment", _("can report comments")),
            ("view_all_comments", _("can view all comments")),
            ("add_comment_with_profile", _("can add comments with profile")),
        ]
        verbose_name = _("comment")
        verbose_name_plural = _("comments")

    def __str__(self):
        return "Comment #%s by %s" % (self.id, self.user_id)

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import CommentObjectType

        return CommentObjectType


class Comment(AbstractComment):
    class Meta(AbstractComment.Meta):
        abstract = False
        swappable = swapper.swappable_setting("baseapp_comments", "Comment")


SwappedComment = swapper.load_model(
    "baseapp_comments", "Comment", required=False, require_ready=False
)


class CommentableModel(AbstractCommentableModel):
    comments = GenericRelation(
        SwappedComment,
        verbose_name=_("comments"),
        content_type_field="target_content_type",
        object_id_field="target_object_id",
    )

    class Meta:
        abstract = True
