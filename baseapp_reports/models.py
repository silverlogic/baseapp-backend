import swapper
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql import RelayModel
from baseapp_core.models import DocumentId, DocumentIdMixin


def default_reports_count():
    return {"total": 0}


def default_reports_count_full():
    d = default_reports_count()

    ReportTypeModel = swapper.load_model("baseapp_reports", "ReportType")

    for report_type in ReportTypeModel.objects.all():
        d[report_type.key] = 0

    return d


class AbstractReportType(DocumentIdMixin, RelayModel, TimeStampedModel):
    key = models.CharField(max_length=255, unique=True)
    label = models.CharField(max_length=255)
    content_types = models.ManyToManyField(
        ContentType,
        blank=True,
        related_name="report_types",
    )
    parent_type = models.ForeignKey(
        swapper.get_model_name("baseapp_reports", "ReportType"),
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="sub_types",
    )

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_reports", "ReportType")

    def __str__(self):
        return self.label

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import ReportTypeObjectType

        return ReportTypeObjectType


class AbstractReport(DocumentIdMixin, RelayModel, TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="reports",
        on_delete=models.CASCADE,
    )
    report_type = models.ForeignKey(
        swapper.get_model_name("baseapp_reports", "ReportType"),
        related_name="reports",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    report_subject = models.TextField(blank=True, null=True)

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
        abstract = True
        swappable = swapper.swappable_setting("baseapp_reports", "Report")
        unique_together = [["user", "target_content_type", "target_object_id"]]
        indexes = [
            models.Index(fields=["target_content_type", "target_object_id"]),
        ]

    def __str__(self):
        return "Report (%s) #%s by %s" % (
            self.report_type,
            self.id,
            self.user.first_name,
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.update_reports_count(self.target)

    def delete(self, *args, **kwargs):
        target = self.target
        super().delete(*args, **kwargs)
        self.update_reports_count(target)

    @classmethod
    def update_reports_count(cls, target):
        """Recompute and persist ``reports_count`` on ``ReportableMetadata`` for ``target``."""
        if not target:
            return

        ReportableMetadata = swapper.load_model("baseapp_reports", "ReportableMetadata")
        metadata = ReportableMetadata.get_or_create_for_object(target)
        if metadata is None:
            return

        counts = default_reports_count_full()
        target_content_type = ContentType.objects.get_for_model(target)
        rows = (
            cls.objects.filter(
                target_content_type=target_content_type,
                target_object_id=target.pk,
                report_type__isnull=False,
            )
            .values("report_type__key")
            .annotate(n=Count("id"))
        )
        for row in rows:
            key = row["report_type__key"]
            n = row["n"]
            if key in counts:
                counts[key] = n
            counts["total"] += n

        metadata.reports_count = counts
        metadata.save(update_fields=["reports_count", "modified"])

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import ReportObjectType

        return ReportObjectType


class AbstractReportableMetadata(TimeStampedModel):
    """
    Stores reporting metadata (per-type counts) for any documentable object.
    Linked to ``DocumentId`` instead of adding columns to each reportable model,
    following the plugin architecture pattern for loose coupling.
    """

    target = models.OneToOneField(
        DocumentId,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="reportable_metadata",
    )
    reports_count = models.JSONField(
        default=default_reports_count,
        verbose_name=_("reports count"),
        editable=False,
    )

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_reports", "ReportableMetadata")
        verbose_name = _("reportable metadata")
        verbose_name_plural = _("reportable metadata")

    def __str__(self):
        return f"ReportableMetadata for {self.target}"

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
        Annotate ``queryset`` with reportable metadata to prevent N+1 queries when
        resolving ``reports_count`` for many rows of the same model.
        Adds ``_reportable_reports_count`` (zero-total dict when no metadata row exists).
        """
        model_cls = queryset.model
        ct_id = ContentType.objects.get_for_model(model_cls).pk
        metadata_qs = cls.objects.filter(
            target__content_type_id=ct_id,
            target__object_id=OuterRef("pk"),
        )
        return queryset.annotate(
            _reportable_reports_count=Coalesce(
                Subquery(metadata_qs.values("reports_count")[:1]),
                Value(default_reports_count(), output_field=models.JSONField()),
            ),
        )
