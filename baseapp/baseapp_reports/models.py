import swapper
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql import RelayModel


def default_reports_count():
    ReportModel = swapper.load_model("baseapp_reports", "Report")

    d = {"total": 0}

    for report_type in ReportModel.ReportTypes:
        d[report_type.name] = 0

    return d


class AbstractBaseReport(RelayModel, TimeStampedModel):
    class ReportTypes(models.IntegerChoices):
        SPAM = 1, _("Spam")
        INAPPROPRIATE = 2, _("Inappropriate")
        FAKE = 3, _("Fake")
        OTHER = 4, _("Other")

        @property
        def description(self):
            return self.label

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="reports",
        on_delete=models.CASCADE,
    )
    report_type = models.IntegerField(choices=ReportTypes.choices, null=True, blank=True)
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
    counts = default_reports_count()
    ReportModel = swapper.load_model("baseapp_reports", "Report")
    target_content_type = ContentType.objects.get_for_model(target)
    for report_type in ReportModel.ReportTypes:
        # TO DO: improve performance by removing the FOR and making 1 query to return counts for all types at once
        counts[report_type.name] = ReportModel.objects.filter(
            target_content_type=target_content_type,
            target_object_id=target.pk,
            report_type=report_type,
        ).count()
        counts["total"] += counts[report_type.name]

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
