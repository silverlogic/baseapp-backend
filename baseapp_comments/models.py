import pghistory
import pgtrigger
import swapper
from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import OuterRef, Subquery
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql import RelayModel
from baseapp_core.models import DocumentId, DocumentIdMixin
from baseapp_core.pghelpers import pghistory_register_default_track
from baseapp_core.plugins import apply_if_installed
from baseapp_core.swapper import init_swapped_models

from .validators import blocked_words_validator


class CommentStatus(models.IntegerChoices):
    DELETED = 0, _("deleted")
    PUBLISHED = 1, _("published")


class NonDeletedComments(models.Manager):
    """Automatically filters out soft deleted objects from QuerySets"""

    def get_queryset(self):
        return super(NonDeletedComments, self).get_queryset().exclude(status=CommentStatus.DELETED)

    def for_target(self, obj, *, root_only=True):
        """
        Top-level (or all) non-deleted comments for a target object, without requiring a reverse
        GenericRelation on the target model. Mirrors the queryset used for GraphQL
        `CommentsInterface` for non-Comment targets (e.g. pages).
        """
        ct = ContentType.objects.get_for_model(obj)
        qs = self.get_queryset().filter(
            target_document__content_type=ct, target_document__object_id=obj.pk
        )
        if root_only:
            qs = qs.filter(in_reply_to__isnull=True)
        return qs


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


if apps.is_installed("baseapp_reactions"):
    from baseapp_reactions.models import ReactableModel

    comment_inheritances.append(ReactableModel)


if apps.is_installed("baseapp_reports"):
    from baseapp_reports.models import ReportableModel

    comment_inheritances.append(ReportableModel)


class AbstractComment(
    *comment_inheritances,
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

    target_document = models.ForeignKey(
        DocumentId,
        verbose_name=_("target document"),
        blank=True,
        null=False,
        related_name="comments_inbox",
        on_delete=models.CASCADE,
    )

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

    def __str__(self):
        return "Comment #%s by %s" % (self.id, self.user_id)

    def _get_target(self):
        if not self.target_document_id:
            return None
        if hasattr(self, "_target_object_cache"):
            return self._target_object_cache
        self._target_object_cache = self.target_document.content_object
        return self._target_object_cache

    _get_target.short_description = _("target")

    def _set_target(self, value):
        if not value:
            self.target_document = None
            self._target_object_cache = None
            return
        self.target_document = DocumentId.get_or_create_for_object(value)
        self._target_object_cache = value

    target = property(_get_target, _set_target)

    @property
    def target_content_type(self):
        if self.target_document_id:
            return self.target_document.content_type
        return None

    @property
    def target_content_type_id(self):
        if self.target_document_id:
            return self.target_document.content_type_id
        return None

    @property
    def target_object_id(self):
        if self.target_document_id:
            return self.target_document.object_id
        return None

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import CommentObjectType

        return CommentObjectType


def default_comments_count():
    return {
        "total": 0,
        "main": 0,
        "replies": 0,
        "pinned": 0,
        "reported": 0,
    }


class AbstractCommentableMetadata(models.Model):
    """
    Stores commenting metadata (count + enabled flag) for any documentable object.
    Linked to DocumentId instead of adding columns to each commentable model,
    following the plugin architecture pattern for loose coupling.
    """

    target = models.OneToOneField(
        DocumentId,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="commentable_metadata",
    )
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

    def __str__(self):
        return f"CommentableMetadata for {self.target}"

    @classmethod
    def get_for_object(cls, obj):
        """Return the metadata for the given object, or None if not found."""
        if not obj or not getattr(obj, "pk", None):
            return None
        try:
            ct = ContentType.objects.get_for_model(obj)
            return cls.objects.get(target__content_type=ct, target__object_id=obj.pk)
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_or_create_for_object(cls, obj):
        """Return or create the metadata for the given object."""
        if not obj or not getattr(obj, "pk", None):
            return None
        doc_id = DocumentId.get_or_create_for_object(obj)
        if doc_id:
            metadata, _ = cls.objects.get_or_create(target=doc_id)
            return metadata
        return None

    @classmethod
    def annotate_queryset(cls, queryset):
        """
        Annotate a queryset with commentable metadata to prevent N+1 queries.
        Adds _commentable_comments_count and _commentable_is_comments_enabled annotations.
        """
        ct = ContentType.objects.get_for_model(queryset.model)
        metadata_qs = cls.objects.filter(
            target__content_type=ct,
            target__object_id=OuterRef("pk"),
        )
        return queryset.annotate(
            _commentable_comments_count=Subquery(metadata_qs.values("comments_count")[:1]),
            _commentable_is_comments_enabled=Subquery(
                metadata_qs.values("is_comments_enabled")[:1],
                output_field=models.BooleanField(),
            ),
        )


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
    exclude=["reactions_count", "modified"],
)
