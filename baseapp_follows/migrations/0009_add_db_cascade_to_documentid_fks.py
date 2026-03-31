import swapper
from django.db import migrations

from baseapp_core.db_utils import DOCUMENTID_TABLE, replace_fk_constraint


def add_db_level_cascade(apps, schema_editor):
    """
    Add ON DELETE CASCADE at the database level for FK constraints pointing to DocumentId.

    Django's on_delete=CASCADE only works at the ORM level. The DocumentIdMixin
    uses pgtriggers that delete DocumentId rows via raw SQL, bypassing Django's
    cascade. This migration makes the DB constraints match the intended behavior.
    """
    FollowStats = apps.get_model("baseapp_follows", "FollowStats")

    with schema_editor.connection.cursor() as cursor:
        replace_fk_constraint(
            schema_editor,
            cursor,
            FollowStats._meta.db_table,
            "target_id",
            DOCUMENTID_TABLE,
            on_delete_cascade=True,
        )

        if not swapper.is_swapped("baseapp_follows", "Follow"):
            Follow = apps.get_model("baseapp_follows", "Follow")
            follow_table = Follow._meta.db_table
            replace_fk_constraint(
                schema_editor,
                cursor,
                follow_table,
                "actor_id",
                DOCUMENTID_TABLE,
                on_delete_cascade=True,
            )
            replace_fk_constraint(
                schema_editor,
                cursor,
                follow_table,
                "target_id",
                DOCUMENTID_TABLE,
                on_delete_cascade=True,
            )


def remove_db_level_cascade(apps, schema_editor):
    """Reverse: restore FK constraints without ON DELETE CASCADE."""
    FollowStats = apps.get_model("baseapp_follows", "FollowStats")

    with schema_editor.connection.cursor() as cursor:
        replace_fk_constraint(
            schema_editor,
            cursor,
            FollowStats._meta.db_table,
            "target_id",
            DOCUMENTID_TABLE,
            on_delete_cascade=False,
        )

        if not swapper.is_swapped("baseapp_follows", "Follow"):
            Follow = apps.get_model("baseapp_follows", "Follow")
            follow_table = Follow._meta.db_table
            replace_fk_constraint(
                schema_editor,
                cursor,
                follow_table,
                "actor_id",
                DOCUMENTID_TABLE,
                on_delete_cascade=False,
            )
            replace_fk_constraint(
                schema_editor,
                cursor,
                follow_table,
                "target_id",
                DOCUMENTID_TABLE,
                on_delete_cascade=False,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_core", "0001_initial"),
        ("baseapp_follows", "0008_create_followstats_remap_fks"),
        swapper.dependency("baseapp_follows", "Follow"),
    ]

    operations = [
        migrations.RunPython(
            add_db_level_cascade,
            remove_db_level_cascade,
        ),
    ]
