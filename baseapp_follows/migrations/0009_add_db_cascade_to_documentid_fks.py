from django.db import migrations

DOCUMENTID_TABLE = "baseapp_core_documentid"


def _get_fk_constraints_referencing_documentid(cursor, table, column):
    """Find FK constraint names on (table, column) that reference baseapp_core_documentid."""
    cursor.execute(
        """
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
          AND tc.table_name = kcu.table_name
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
        WHERE tc.table_name = %s
          AND kcu.column_name = %s
          AND tc.constraint_type = 'FOREIGN KEY'
          AND ccu.table_name = %s
        """,
        [table, column, DOCUMENTID_TABLE],
    )
    return [row[0] for row in cursor.fetchall()]


def _replace_fk_constraint(schema_editor, cursor, table, column, on_delete_cascade):
    """Drop and recreate a FK constraint with or without ON DELETE CASCADE."""
    constraint_names = _get_fk_constraints_referencing_documentid(cursor, table, column)

    if not constraint_names:
        # FK doesn't reference DocumentId yet (e.g. swapped model migration hasn't run)
        return

    for constraint_name in constraint_names:
        schema_editor.execute(
            "ALTER TABLE %s DROP CONSTRAINT %s"
            % (
                schema_editor.quote_name(table),
                schema_editor.quote_name(constraint_name),
            )
        )

    new_constraint_name = "%s_%s_fk_documentid" % (table, column)
    if len(new_constraint_name) > 63:
        new_constraint_name = new_constraint_name[:63]

    on_delete_clause = "ON DELETE CASCADE " if on_delete_cascade else ""

    schema_editor.execute(
        "ALTER TABLE %s ADD CONSTRAINT %s "
        "FOREIGN KEY (%s) REFERENCES %s (id) "
        "%sDEFERRABLE INITIALLY DEFERRED"
        % (
            schema_editor.quote_name(table),
            schema_editor.quote_name(new_constraint_name),
            schema_editor.quote_name(column),
            schema_editor.quote_name(DOCUMENTID_TABLE),
            on_delete_clause,
        )
    )


def add_db_level_cascade(apps, schema_editor):
    """
    Add ON DELETE CASCADE at the database level for FollowStats FK to DocumentId.

    Django's on_delete=CASCADE only works at the ORM level. The DocumentIdMixin
    uses pgtriggers that delete DocumentId rows via raw SQL, bypassing Django's
    cascade. This migration makes the DB constraint match the intended behavior.

    Note: For swapped Follow models, the consumer app must create its own
    migration to add CASCADE to the Follow table's FKs.
    """
    FollowStats = apps.get_model("baseapp_follows", "FollowStats")
    followstats_table = FollowStats._meta.db_table

    with schema_editor.connection.cursor() as cursor:
        _replace_fk_constraint(
            schema_editor, cursor, followstats_table, "target_id", on_delete_cascade=True
        )


def remove_db_level_cascade(apps, schema_editor):
    """Reverse: restore FK constraint without ON DELETE CASCADE."""
    FollowStats = apps.get_model("baseapp_follows", "FollowStats")
    followstats_table = FollowStats._meta.db_table

    with schema_editor.connection.cursor() as cursor:
        _replace_fk_constraint(
            schema_editor, cursor, followstats_table, "target_id", on_delete_cascade=False
        )


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_core", "0001_initial"),
        ("baseapp_follows", "0008_create_followstats_remap_fks"),
    ]

    operations = [
        migrations.RunPython(
            add_db_level_cascade,
            remove_db_level_cascade,
        ),
    ]
