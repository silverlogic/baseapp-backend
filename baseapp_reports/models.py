import swapper
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from model_utils.models import TimeStampedModel

from baseapp_core.graphql import RelayModel


def default_reports_count():
    return {"total": 0}


def default_reports_count_full():
    d = default_reports_count()

    ReportTypeModel = swapper.load_model("baseapp_reports", "ReportType")

    for report_type in ReportTypeModel.objects.all():
        d[report_type.key] = 0

    return d


class AbstractBaseReportType(RelayModel, TimeStampedModel):
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

    def __str__(self):
        return self.label


class ReportType(AbstractBaseReportType):
    class Meta(AbstractBaseReportType.Meta):
        swappable = swapper.swappable_setting("baseapp_reports", "ReportType")

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import ReportTypeObjectType

        return ReportTypeObjectType


class AbstractBaseReport(RelayModel, TimeStampedModel):
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

        update_reports_count(self.target)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)

        update_reports_count(self.target)


class Report(AbstractBaseReport):
    class Meta(AbstractBaseReport.Meta):
        swappable = swapper.swappable_setting("baseapp_reports", "Report")

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import ReportObjectType

        return ReportObjectType


def update_reports_count(target):
    if not target:
        return
    counts = default_reports_count_full()
    ReportModel = swapper.load_model("baseapp_reports", "Report")
    ReportTypeModel = swapper.load_model("baseapp_reports", "ReportType")
    target_content_type = ContentType.objects.get_for_model(target)
    for report_type in ReportTypeModel.objects.all():
        # TO DO: improve performance by removing the FOR and making 1 query to return counts for all types at once
        counts[report_type.key] = ReportModel.objects.filter(
            target_content_type=target_content_type,
            target_object_id=target.pk,
            report_type=report_type,
        ).count()
        counts["total"] += counts[report_type.key]

    target.reports_count = counts
    target.save(update_fields=["reports_count"])


SwappedReport = swapper.load_model("baseapp_reports", "Report", required=False, require_ready=False)


class ReportableModel(models.Model):
    reports_count = models.JSONField(default=default_reports_count)
    reports = GenericRelation(
        SwappedReport,
        content_type_field="target_content_type",
        object_id_field="target_object_id",
    )

    class Meta:
        abstract = True
