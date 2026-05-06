import django.db.models.deletion
import django.utils.timezone
import model_utils.fields
from django.db import migrations, models

import baseapp_reports.models


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_core", "0001_initial"),
        ("reports", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReportableMetadata",
            fields=[
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="modified",
                    ),
                ),
                (
                    "target",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="reportable_metadata",
                        serialize=False,
                        to="baseapp_core.documentid",
                    ),
                ),
                (
                    "reports_count",
                    models.JSONField(
                        default=baseapp_reports.models.default_reports_count,
                        editable=False,
                        verbose_name="reports count",
                    ),
                ),
            ],
            options={
                "verbose_name": "reportable metadata",
                "verbose_name_plural": "reportable metadata",
                "abstract": False,
            },
        ),
    ]
