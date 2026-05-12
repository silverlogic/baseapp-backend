from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


def alter_data_column_to_jsonb(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """Cast the ``data`` column from text (jsonfield) to jsonb (Django JSONField) on PostgreSQL.

    This migration targets existing databases that ran 0001_initial before the
    ``data`` field was changed from ``jsonfield.fields.JSONField`` (stored as
    ``text``) to Django's native ``models.JSONField`` (stored as ``jsonb`` on
    PostgreSQL).  Fresh installs where 0001 already creates a ``jsonb`` column
    are handled safely: the check against ``information_schema`` skips the
    ALTER when the column is already the correct type.

    On non-PostgreSQL backends the column types are compatible and no explicit
    cast is needed, so this function returns immediately.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    Notification = apps.get_model("baseapp_notifications", "Notification")
    table = Notification._meta.db_table
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s AND column_name = 'data'",
            [table],
        )
        row = cursor.fetchone()
    if row and row[0] == "text":
        quoted_table = schema_editor.connection.ops.quote_name(table)
        schema_editor.execute(
            f'ALTER TABLE {quoted_table} ALTER COLUMN "data" TYPE jsonb USING data::jsonb'
        )


def reverse_alter_data_column_to_text(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """Reverse migration: cast ``data`` back from jsonb to text.

    Only executes the ALTER when the column is not already ``jsonb``.  On a
    fresh install ``0001_initial`` creates the column as ``jsonb`` directly, so
    the forward migration was a no-op; reversing it must also be a no-op to
    avoid incorrectly casting an already-correct ``jsonb`` column to ``text``.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    Notification = apps.get_model("baseapp_notifications", "Notification")
    table = Notification._meta.db_table
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s AND column_name = 'data'",
            [table],
        )
        row = cursor.fetchone()
    if row and row[0] != "jsonb":
        quoted_table = schema_editor.connection.ops.quote_name(table)
        schema_editor.execute(
            f'ALTER TABLE {quoted_table} ALTER COLUMN "data" TYPE text USING data::text'
        )


class Migration(migrations.Migration):
    """
    Migrate the ``data`` column on Notification from ``text`` (written by
    ``jsonfield.fields.JSONField`` used in 0001_initial) to ``jsonb``
    (Django's native ``models.JSONField``) on PostgreSQL.

    0001_initial was updated to use ``models.JSONField`` so that fresh
    installs create the column as ``jsonb`` from the start.  This migration
    handles existing databases that already applied 0001_initial with the old
    ``text`` column by performing the DDL cast at upgrade time.
    """

    dependencies = [
        ("baseapp_notifications", "0005_alter_notification_level_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # Perform the actual DDL cast on PostgreSQL for existing databases.
            database_operations=[
                migrations.RunPython(
                    alter_data_column_to_jsonb,
                    reverse_alter_data_column_to_text,
                ),
            ],
            # The Django migration state was already updated in 0001_initial
            # (models.JSONField), so no state change is needed here.
            state_operations=[],
        ),
    ]
