import pghistory
import swapper
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _
from django_quill.fields import QuillField
from model_utils.models import TimeStampedModel
from translated_fields import TranslatedField

from baseapp_comments.models import CommentableModel
from baseapp_core.graphql.models import RelayModel
from baseapp_core.models import random_name_in


class URLPath(TimeStampedModel, RelayModel):
    path = models.CharField(max_length=500, unique=True)
    language = models.CharField(max_length=10, choices=settings.LANGUAGES, null=True, blank=True)
    is_active = models.BooleanField(default=False)

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
        indexes = [
            models.Index(fields=["target_content_type", "target_object_id"]),
        ]
        verbose_name = "URL Path"
        verbose_name_plural = "URL Paths"
        constraints = [
            models.UniqueConstraint(
                condition=models.Q(is_active=True),
                fields=["path", "language"],
                name="unique_active_path",
            )
        ]

    def __str__(self):
        return self.path


@pghistory.track(
    pghistory.InsertEvent(),
    pghistory.UpdateEvent(),
    pghistory.DeleteEvent(),
)
class Metadata(TimeStampedModel, RelayModel):
    target_content_type = models.ForeignKey(
        ContentType,
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    target_object_id = models.PositiveIntegerField(blank=True, null=True)
    target = GenericForeignKey("target_content_type", "target_object_id")

    language = models.CharField(choices=settings.LANGUAGES, max_length=10, null=True, blank=True)

    meta_title = models.CharField(_("meta title"), max_length=255, null=True, blank=True)
    meta_description = models.TextField(
        _("meta description"), max_length=500, null=True, blank=True
    )
    meta_robots = models.CharField(max_length=100, null=True, blank=True)

    meta_og_type = models.CharField(max_length=100, null=True, blank=True)
    meta_og_image = models.ImageField(
        upload_to=random_name_in("pages/metadata/og_image"), blank=True, null=True
    )

    class Meta:
        unique_together = ("target_content_type", "target_object_id", "language")


class PageMixin(models.Model):
    url_paths = GenericRelation(
        URLPath,
        content_type_field="target_content_type",
        object_id_field="target_object_id",
    )

    metadatas = GenericRelation(
        Metadata,
        content_type_field="target_content_type",
        object_id_field="target_object_id",
    )

    class Meta:
        abstract = True

    @property
    def url_path(self):
        # returns the most probable url path based on current session
        return self.url_paths.filter(
            Q(is_active=True), Q(language=get_language()) | Q(language__isnull=True)
        ).first()


class AbstractPage(PageMixin, TimeStampedModel, RelayModel, CommentableModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="pages",
        on_delete=models.CASCADE,
        verbose_name=_("user"),
        null=True,
        blank=True,
    )

    title = TranslatedField(models.CharField(_("title"), max_length=255, blank=True, null=True))
    body = TranslatedField(QuillField(_("body"), blank=True, null=True))

    class PageStatus(models.IntegerChoices):
        DRAFT = 1, _("Draft")
        PUBLISHED = 2, _("Published")

        @property
        def description(self):
            return self.label

    status = models.IntegerField(
        choices=PageStatus.choices, default=PageStatus.PUBLISHED, db_index=True
    )

    class Meta:
        abstract = True

    def __str__(self):
        return self.title or str(self.pk)


def conditional_decorator(dec, condition):
    def decorator(func):
        if not condition:
            # Return the function unchanged, not decorated.
            return func
        return dec(func)

    return decorator


class Page(AbstractPage):
    class Meta:
        swappable = swapper.swappable_setting("baseapp_pages", "Page")

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import PageObjectType

        return PageObjectType
