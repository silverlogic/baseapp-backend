from typing import TYPE_CHECKING

import pghistory
import pgtrigger
import swapper
from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import IntegerField, OuterRef, Subquery, Value
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
from baseapp_core.pghelpers import pghistory_register_default_track
from baseapp_core.plugins import apply_if_installed
from baseapp_core.swapper import init_swapped_models

from .validators import blocked_words_validator

if TYPE_CHECKING:
    from baseapp_core.graphql import DjangoObjectType


class CommentStatus(models.IntegerChoices):
    DELETED = 0, _("deleted")
    PUBLISHED = 1, _("published")


class CommentQuerySet(models.QuerySet):
    def visible(self) -> "CommentQuerySet":
        return self.exclude(status=CommentStatus.DELETED)

    def for_target(self, obj, *, root_only=True) -> "CommentQuerySet":
        ct = ContentType.objects.get_for_model(obj)

        qs = self.visible().filter(
            target_document__content_type=ct,
            target_document__object_id=obj.pk,
        )

        if root_only:
            qs = qs.filter(in_reply_to__isnull=True)

        return qs


class NonDeletedComments(models.Manager):
    """Automatically filters out soft deleted objects from QuerySets"""

    def get_queryset(self) -> CommentQuerySet:
        return CommentQuerySet(self.model, using=self._db).visible()

    def for_target(self, obj, *, root_only=True) -> CommentQuerySet:
        return self.get_queryset().for_target(obj, root_only=root_only)


comment_inheritances = []

if apps.is_installed("baseapp_profiles"):

    class ProfileMixin(models.Model):
        profile = models.ForeignKey(
            swapper.get_model_name("baseapp_profiles", "Profile"),
            verbose_name=_("profile"),
            related_name="comments",
            on_delete=models.SET_NULL,
            null=True,
            blank=True,
        )

        class Meta:
            abstract = True

    comment_inheritances.append(ProfileMixin)


class AbstractComment(
    *comment_inheritances,
    DocumentIdTargetMixin,
    DocumentIdMixin,
    RelayModel,
    TimeStampedModel,
):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        related_name="comments",
        on_delete=models.SET_NULL,
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

    objects = CommentQuerySet.as_manager()
    objects_visible = NonDeletedComments()

    class Meta:
        abstract = True
        ordering = ["-is_pinned", "-created"]
        indexes = [
            models.Index(
                fields=[
                    "target_document",
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
            *apply_if_installed(
                "baseapp_profiles",
                [("add_comment_with_profile", _("can add comments with profile"))],
            ),
        ]
        verbose_name = _("comment")
        verbose_name_plural = _("comments")

    def __str__(self) -> str:
        return "Comment #%s by %s" % (self.id, self.user_id)

    @classmethod
    def get_graphql_object_type(cls) -> type["DjangoObjectType"]:
        from .graphql.object_types import CommentObjectType

        return CommentObjectType


def default_comments_count() -> dict[str, int]:
    return {
        "total": 0,
        "main": 0,
        "replies": 0,
        "pinned": 0,
        "reported": 0,
    }


class AbstractCommentableMetadata(DocumentIdUniqueTargetMixin, TimeStampedModel):
    """
    Stores commenting metadata (count + enabled flag) for any documentable object.
    Linked to DocumentId instead of adding columns to each commentable model,
    following the plugin architecture pattern for loose coupling.
    """

    comments_count = models.JSONField(
        default=default_comments_count,
        verbose_name=_("comments count"),
        editable=False,
    )
    is_comments_enabled = models.BooleanField(
        default=True,
        verbose_name=_("is comments enabled"),
    )

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_comments", "CommentableMetadata")
        verbose_name = _("commentable metadata")
        verbose_name_plural = _("commentable metadata")

    def __str__(self) -> str:
        return f"CommentableMetadata for {self.target}"

    @classmethod
    def annotate_queryset(cls, queryset) -> models.QuerySet:
        """
        Annotate a queryset with commentable metadata to prevent N+1 queries.
        Adds _commentable_comments_count and _commentable_is_comments_enabled.
        For Comment querysets only, also adds replies_count_total (CommentFilter / ordering).
        Resolves the model ContentType id once per call (Django's ContentType manager caches
        until ContentType.objects.clear_cache()).
        """
        model_cls = queryset.model
        ct_id = ContentType.objects.get_for_model(model_cls).pk
        metadata_qs = cls.objects.filter(
            target__content_type_id=ct_id,
            target__object_id=OuterRef("pk"),
        )
        annotations = {
            "_commentable_comments_count": Subquery(metadata_qs.values("comments_count")[:1]),
            "_commentable_is_comments_enabled": Subquery(
                metadata_qs.values("is_comments_enabled")[:1],
                output_field=models.BooleanField(),
            ),
        }
        CommentModel = swapper.load_model("baseapp_comments", "Comment")
        if model_cls is CommentModel:
            replies_total_sq = metadata_qs.annotate(
                _reply_total=Cast(
                    KeyTextTransform("total", "comments_count"),
                    output_field=IntegerField(),
                )
            ).values("_reply_total")[:1]
            annotations["replies_count_total"] = Coalesce(
                Subquery(replies_total_sq, output_field=IntegerField()),
                Value(0),
            )
        return queryset.annotate(**annotations)


# Both init_swapped_models calls are placed here so that when the first one (Comment)
# triggers testproject/comments/models.py to load, both AbstractComment AND
# AbstractCommentableMetadata are already fully defined above.
Comment = init_swapped_models(
    [
        ("baseapp_comments", "Comment"),
    ]
)

CommentableMetadata = init_swapped_models(
    [
        ("baseapp_comments", "CommentableMetadata"),
    ]
)


pghistory_register_default_track(
    Comment,
    pghistory.InsertEvent(),
    pghistory.UpdateEvent(),
    pghistory.DeleteEvent(),
    exclude=["modified"],
)
