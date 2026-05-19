import swapper
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_blocks.base import AbstractBlock  # noqa: F401
from baseapp_core.models import DocumentId


class AbstractBlockableMetadata(TimeStampedModel):
    """
    Stores blockable metadata (blocker / blocking counts) for any documentable
    object. Linked to `DocumentId` instead of adding columns to each blockable
    model, following the plugin architecture pattern.
    """

    target = models.OneToOneField(
        DocumentId,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="blockable_metadata",
    )
    blockers_count = models.PositiveIntegerField(default=0, editable=False)
    blocking_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_blocks", "BlockableMetadata")
        verbose_name = _("blockable metadata")
        verbose_name_plural = _("blockable metadata")

    def __str__(self):
        return f"BlockableMetadata for {self.target}"

    @classmethod
    def get_for_object(cls, obj):
        """Return the metadata for the given object, or `None` if not found."""
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
        Annotate `queryset` with blockable metadata so resolvers don't N+1.
        Adds `_blockable_blockers_count` and `_blockable_blocking_count`,
        both `Coalesce`'d to 0 so consumer-side ORDER BY can sort on a real
        expression.
        """
        model_cls = queryset.model
        ct_id = ContentType.objects.get_for_model(model_cls).pk
        metadata_qs = cls.objects.filter(
            target__content_type_id=ct_id,
            target__object_id=OuterRef("pk"),
        )
        return queryset.annotate(
            _blockable_blockers_count=Coalesce(
                Subquery(
                    metadata_qs.values("blockers_count")[:1],
                    output_field=models.PositiveIntegerField(),
                ),
                Value(0),
            ),
            _blockable_blocking_count=Coalesce(
                Subquery(
                    metadata_qs.values("blocking_count")[:1],
                    output_field=models.PositiveIntegerField(),
                ),
                Value(0),
            ),
        )
