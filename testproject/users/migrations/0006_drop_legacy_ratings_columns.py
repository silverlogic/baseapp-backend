"""
Drop the legacy ``ratings_count`` / ``ratings_sum`` / ``ratings_average`` /
``is_ratings_enabled`` columns from User. They lived on User because User used to
inherit ``baseapp_ratings.models.RatableModel`` (now removed). Rating counters live
on ``RatableMetadata`` from now on, populated via the metadata service.
"""

from django.db import migrations

from baseapp_ratings.migration_helpers.convert_legacy_ratings_count_to_metadata_helper import (
    migrate_legacy_ratings_to_metadata,
    reverse_migrate_legacy_ratings_from_metadata,
)


def migrate_user_ratings(apps, schema_editor):
    migrate_legacy_ratings_to_metadata(
        apps,
        schema_editor,
        source_app_label="users",
        source_model_name="User",
        metadata_app_label="ratings",
    )


def reverse_migrate_user_ratings(apps, schema_editor):
    reverse_migrate_legacy_ratings_from_metadata(
        apps,
        schema_editor,
        source_app_label="users",
        source_model_name="User",
        metadata_app_label="ratings",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_user_update_profile_name_user_create_profile"),
        ("ratings", "0002_ratablemetadata"),
    ]

    operations = [
        migrations.RunPython(migrate_user_ratings, reverse_migrate_user_ratings),
        migrations.RemoveField(model_name="user", name="ratings_count"),
        migrations.RemoveField(model_name="user", name="ratings_sum"),
        migrations.RemoveField(model_name="user", name="ratings_average"),
        migrations.RemoveField(model_name="user", name="is_ratings_enabled"),
    ]
