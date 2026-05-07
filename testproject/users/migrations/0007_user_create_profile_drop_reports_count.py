"""
Re-create the ``create_profile`` pgtrigger on ``users_user`` so its INSERT into
``profiles_profile`` no longer references the dropped ``reports_count`` column.

Depends on ``profiles.0006_remove_reports_count`` so the column has actually been
dropped before the trigger SQL referencing it is replaced.
"""

import pgtrigger.compiler
import pgtrigger.migrations
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0006_drop_legacy_ratings_columns"),
        ("profiles", "0006_remove_reports_count"),
    ]

    operations = [
        pgtrigger.migrations.RemoveTrigger(
            model_name="user",
            name="create_profile",
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="user",
            trigger=pgtrigger.compiler.Trigger(
                name="create_profile",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func="\n            IF NEW.profile_id IS NULL THEN\n                WITH new_profile AS (\n                    INSERT INTO profiles_profile (owner_id, target_content_type_id, target_object_id, name, created, modified, blockers_count, blocking_count, status)\n                    VALUES (NEW.id, (SELECT id FROM django_content_type WHERE app_label = 'users' AND model = 'user'), NEW.id, TRIM(COALESCE(NEW.first_name || ' ' || NEW.last_name, '')), NOW(), NOW(), 0, 0, 1)\n                    -- Conflicts arise when a Profile for this object already exists\n                    -- (e.g. seeded by a migration or a prior trigger run).  Refresh\n                    -- owner, name, and modified so the profile stays consistent with\n                    -- the current row rather than silently retaining stale values.\n                    ON CONFLICT (target_content_type_id, target_object_id) DO UPDATE\n                        SET owner_id = EXCLUDED.owner_id,\n                            name     = EXCLUDED.name,\n                            modified = EXCLUDED.modified\n                    RETURNING id\n                )\n                UPDATE users_user SET profile_id = (SELECT id FROM new_profile) WHERE id = NEW.id;\n            END IF;\n            RETURN NULL;\n        ",
                    hash="8b84a7d237a640ab50271b3ede907fc930fc9a3d",
                    operation="INSERT",
                    pgid="pgtrigger_create_profile_2293f",
                    table="users_user",
                    when="AFTER",
                ),
            ),
        ),
    ]
