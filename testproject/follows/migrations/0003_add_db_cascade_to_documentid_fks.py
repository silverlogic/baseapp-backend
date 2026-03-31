import importlib

from django.db import migrations

_migration_0009 = importlib.import_module(
    "baseapp_follows.migrations.0009_add_db_cascade_to_documentid_fks"
)
_replace_follow_fks = _migration_0009._replace_follow_fks


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_core", "0001_initial"),
        ("baseapp_follows", "0009_add_db_cascade_to_documentid_fks"),
        ("follows", "0002_alter_follow_actor_alter_follow_target"),
    ]

    operations = [
        migrations.RunPython(
            lambda apps, se: _replace_follow_fks(apps, se, on_delete_cascade=True),
            lambda apps, se: _replace_follow_fks(apps, se, on_delete_cascade=False),
        ),
    ]
