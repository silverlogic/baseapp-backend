from django.db import migrations

from baseapp_core.db_utils import DOCUMENTID_TABLE, replace_fk_constraint


def add_db_level_cascade(apps, schema_editor):
    """
    Add ON DELETE CASCADE at the database level for Follow FKs to DocumentId.

    Django's on_delete=CASCADE only works at the ORM level. The DocumentIdMixin
    uses pgtriggers that delete DocumentId rows via raw SQL, bypassing Django's
    cascade. This migration makes the DB constraints match the intended behavior.
    """
    Follow = apps.get_model("follows", "Follow")
    follow_table = Follow._meta.db_table

    with schema_editor.connection.cursor() as cursor:
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
    Follow = apps.get_model("follows", "Follow")
    follow_table = Follow._meta.db_table

    with schema_editor.connection.cursor() as cursor:
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
        ("follows", "0002_alter_follow_actor_alter_follow_target"),
    ]

    operations = [
        migrations.RunPython(
            add_db_level_cascade,
            remove_db_level_cascade,
        ),
    ]
