# Backfills Follow.actor/target from legacy Profile primary keys to DocumentId primary keys
# (no-op when no legacy rows exist) and seeds FollowableMetadata from current Follow data.

from django.db import migrations

from baseapp_follows.migration_helpers.convert_follow_profile_fks_into_document_id_helper import (
    migrate_follow_profile_fks_to_document_id,
    reverse_migrate_follow_document_id_fks_to_profile,
)
from baseapp_follows.migration_helpers.seed_followable_metadata_from_follows_helper import (
    reverse_seed_followable_metadata,
    seed_followable_metadata_from_follows,
)


class Migration(migrations.Migration):
    dependencies = [
        ("follows", "0003_followablemetadata"),
    ]

    operations = [
        migrations.RunPython(
            migrate_follow_profile_fks_to_document_id,
            reverse_migrate_follow_document_id_fks_to_profile,
        ),
        migrations.RunPython(
            seed_followable_metadata_from_follows,
            reverse_seed_followable_metadata,
        ),
    ]
