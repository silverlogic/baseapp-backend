# Seeds the default ReportType rows for the testproject. Mirrors the project-side
# seeding migration; consumers are expected to provide their own variant.

from django.db import migrations

from baseapp_reports.migration_helpers.seed_default_report_types_helper import (
    reverse_seed_default_report_types,
    seed_default_report_types,
)

CONTENT_TYPE_TARGETS = {
    "comment": ("comments", "Comment"),
    "page": ("pages", "Page"),
    "profile": ("profiles", "Profile"),
}


def forwards(apps, schema_editor):
    seed_default_report_types(
        apps,
        schema_editor,
        content_type_targets=CONTENT_TYPE_TARGETS,
    )


def backwards(apps, schema_editor):
    reverse_seed_default_report_types(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0002_reportablemetadata"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
