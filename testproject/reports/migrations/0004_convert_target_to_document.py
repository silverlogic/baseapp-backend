"""
Convert ``Report`` targets from the legacy GFK columns
(``target_content_type``, ``target_object_id``) to a single ``target_document`` FK on
``baseapp_core.DocumentId``. Mirrors the comments equivalent
(``testproject/comments/migrations/0007_*``).
"""

import django.db.models.deletion
from django.db import migrations, models

from baseapp_reports.migration_helpers.convert_reports_gfk_into_document_id_helper import (
    migrate_report_targets_to_document_id,
    reverse_migrate_report_targets_to_generic_fk,
)


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_core", "0001_initial"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("reports", "0003_seed_default_report_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="report",
            name="target_document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="reports_inbox",
                to="baseapp_core.documentid",
                verbose_name="target document",
            ),
        ),
        migrations.RunPython(
            migrate_report_targets_to_document_id,
            reverse_migrate_report_targets_to_generic_fk,
        ),
        migrations.AlterField(
            model_name="report",
            name="target_document",
            field=models.ForeignKey(
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="reports_inbox",
                to="baseapp_core.documentid",
                verbose_name="target document",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="report",
            unique_together=set(),
        ),
        migrations.RemoveIndex(
            model_name="report",
            name="baseapp_rep_target__171117_idx",
        ),
        migrations.RemoveField(
            model_name="report",
            name="target_content_type",
        ),
        migrations.RemoveField(
            model_name="report",
            name="target_object_id",
        ),
        migrations.AlterUniqueTogether(
            name="report",
            unique_together={("user", "target_document")},
        ),
    ]
