"""
Reusable migration helpers to (re)build ``FollowableMetadata`` rows from existing ``Follow``
data.

This is useful right after creating the ``FollowableMetadata`` table — both for legacy
projects upgrading from the old ``FollowStats`` schema and for fresh projects that need
their counters seeded from whatever follow rows already exist.

How to use in a project migration
---------------------------------
1. Make sure your migration depends on the migration that creates ``FollowableMetadata``.
2. Add a ``RunPython`` operation that calls
   ``seed_followable_metadata_from_follows(...)``.
3. Use ``reverse_seed_followable_metadata(...)`` (or
   :func:`migrations.RunPython.noop`) as the reverse code.

Example:

    def forwards(apps, schema_editor):
        seed_followable_metadata_from_follows(apps, schema_editor)

    def backwards(apps, schema_editor):
        reverse_seed_followable_metadata(apps, schema_editor)

    migrations.RunPython(forwards, backwards)

Notes
-----
- The helpers resolve models using ``apps.get_model(...)`` / ``get_apps_model(...)`` so they
  are safe in historical migration state, including when ``Follow`` and
  ``FollowableMetadata`` are swapped.
- The forward helper assumes ``Follow.actor`` and ``Follow.target`` already reference
  ``DocumentId``. Run :mod:`convert_follow_profile_fks_into_document_id_helper` first if
  rows still hold ``Profile`` primary keys.
- ``reverse_seed_followable_metadata`` truncates only rows in ``FollowableMetadata`` whose
  ``target_id`` matches a value currently present in ``Follow.actor_id`` or
  ``Follow.target_id``, so unrelated metadata records are preserved.
"""

from baseapp_core.swapper import get_apps_model


def seed_followable_metadata_from_follows(
    apps,
    schema_editor,
    *,
    metadata_app_label: str = "baseapp_follows",
    metadata_model_name: str = "FollowableMetadata",
):
    """
    Create or update one ``FollowableMetadata`` row per ``DocumentId`` that appears as an
    ``actor`` or ``target`` in any ``Follow`` row, populating
    ``followers_count`` / ``following_count`` from a fresh count of the live follow data.
    """
    Follow = get_apps_model(apps, "baseapp_follows", "Follow")
    FollowableMetadata = get_apps_model(apps, metadata_app_label, metadata_model_name)

    target_ids = set(Follow.objects.values_list("target_id", flat=True).distinct())
    actor_ids = set(Follow.objects.values_list("actor_id", flat=True).distinct())
    doc_ids = target_ids | actor_ids

    for doc_id in doc_ids:
        followers_count = Follow.objects.filter(target_id=doc_id).count()
        following_count = Follow.objects.filter(actor_id=doc_id).count()
        FollowableMetadata.objects.update_or_create(
            target_id=doc_id,
            defaults={
                "followers_count": followers_count,
                "following_count": following_count,
            },
        )


def reverse_seed_followable_metadata(
    apps,
    schema_editor,
    *,
    metadata_app_label: str = "baseapp_follows",
    metadata_model_name: str = "FollowableMetadata",
):
    """
    Drop ``FollowableMetadata`` rows that were seeded from existing ``Follow`` data.

    Only rows whose ``target_id`` still appears as an ``actor`` or ``target`` in ``Follow``
    are removed; unrelated metadata rows (created by other migrations, or by post-migrate
    application code) are left untouched.
    """
    Follow = get_apps_model(apps, "baseapp_follows", "Follow")
    FollowableMetadata = get_apps_model(apps, metadata_app_label, metadata_model_name)

    target_ids = set(Follow.objects.values_list("target_id", flat=True).distinct())
    actor_ids = set(Follow.objects.values_list("actor_id", flat=True).distinct())
    doc_ids = target_ids | actor_ids

    if doc_ids:
        FollowableMetadata.objects.filter(target_id__in=doc_ids).delete()
