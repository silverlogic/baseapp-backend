"""
Convert `Rate` targets from the legacy GFK columns
(`target_content_type`, `target_object_id`) to a single `target_document` FK on
`baseapp_core.DocumentId`.
"""

import django.db.models.deletion
from django.db import migrations, models

from baseapp_ratings.migration_helpers.convert_rates_gfk_into_document_id_helper import (
    migrate_rate_targets_to_document_id,
    reverse_migrate_rate_targets_to_generic_fk,
)


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_core", "0001_initial"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("ratings", "0002_ratablemetadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="rate",
            name="target_document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ratings_inbox",
                to="baseapp_core.documentid",
                verbose_name="target document",
            ),
        ),
        migrations.RunPython(
            migrate_rate_targets_to_document_id,
            reverse_migrate_rate_targets_to_generic_fk,
        ),
        migrations.AlterField(
            model_name="rate",
            name="target_document",
            field=models.ForeignKey(
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="ratings_inbox",
                to="baseapp_core.documentid",
                verbose_name="target document",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="rate",
            unique_together=set(),
        ),
        migrations.RemoveIndex(
            model_name="rate",
            name="ratings_rat_target__367d45_idx",
        ),
        migrations.RemoveField(
            model_name="rate",
            name="target_content_type",
        ),
        migrations.RemoveField(
            model_name="rate",
            name="target_object_id",
        ),
        migrations.AlterUniqueTogether(
            name="rate",
            unique_together={("user", "target_document")},
        ),
    ]
