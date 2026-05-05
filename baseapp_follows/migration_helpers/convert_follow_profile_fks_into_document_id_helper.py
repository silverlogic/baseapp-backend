"""
Reusable migration helpers to convert ``Follow.actor`` and ``Follow.target`` from foreign keys
on ``Profile`` (or any single source model) to foreign keys on ``DocumentId``.

This is useful for legacy projects whose ``Follow`` rows still store the underlying
``Profile`` primary key in ``actor_id``/``target_id`` columns.

How to use in a project migration
---------------------------------
1. In your migration, ensure ``Follow.actor`` and ``Follow.target`` already reference
   ``baseapp_core.documentid`` at the schema level (an ``AlterField`` operation that ran
   earlier — Django allows the FK target swap even while the column values are still
   profile PKs because the on-disk type is just an integer).
2. Run a ``RunPython`` operation that calls
   ``migrate_follow_profile_fks_to_document_id(...)`` BEFORE any subsequent operation
   relies on ``actor`` or ``target`` resolving to a real ``DocumentId``.
3. Optionally pass ``reverse_migrate_follow_document_id_fks_to_profile(...)`` as the
   reverse code so a downgrade can restore the original profile PKs.

Example:

    def forwards(apps, schema_editor):
        migrate_follow_profile_fks_to_document_id(
            apps,
            schema_editor,
            source_app_label="profiles",
            source_model_name="Profile",
        )

    def backwards(apps, schema_editor):
        reverse_migrate_follow_document_id_fks_to_profile(
            apps,
            schema_editor,
            source_app_label="profiles",
            source_model_name="Profile",
        )

    migrations.RunPython(forwards, backwards)

Notes
-----
- The helpers resolve models using ``apps.get_model(...)`` / ``get_apps_model(...)`` so they
  are safe in historical migration state, including when ``Follow`` is swapped.
- Rows whose ``actor_id``/``target_id`` cannot be resolved to an existing ``DocumentId`` are
  removed; they are orphaned data that can no longer satisfy the FK to ``DocumentId``.
- After the backfill the helper asserts every remaining ``Follow`` row has both ``actor_id``
  and ``target_id`` pointing at a row in ``baseapp_core_documentid``, so the project
  migration can rely on the FK being valid before tightening constraints.
"""

from baseapp_core.swapper import get_apps_model


def assert_all_follow_rows_reference_document_ids(apps, schema_editor=None) -> None:
    """
    Fail if any ``Follow`` row still has an ``actor_id`` or ``target_id`` that is not present
    in ``baseapp_core_documentid``. Called at the end of
    :func:`migrate_follow_profile_fks_to_document_id`.
    """
    Follow = get_apps_model(apps, "baseapp_follows", "Follow")
    DocumentId = apps.get_model("baseapp_core", "DocumentId")

    if schema_editor is not None and getattr(schema_editor, "connection", None) is not None:
        alias = schema_editor.connection.alias
        f_qs = Follow.objects.using(alias)
        d_qs = DocumentId.objects.using(alias)
    else:
        f_qs = Follow.objects
        d_qs = DocumentId.objects

    valid_ids = set(d_qs.values_list("id", flat=True))
    bad = [f for f in f_qs.all() if f.actor_id not in valid_ids or f.target_id not in valid_ids]
    if bad:
        raise ValueError(
            f"Follow profile-FK migration: {len(bad)} row(s) still reference "
            "actor/target IDs that are not present in baseapp_core_documentid."
        )


def migrate_follow_profile_fks_to_document_id(
    apps,
    schema_editor,
    *,
    source_app_label: str = "baseapp_profiles",
    source_model_name: str = "Profile",
):
    """
    Remap ``Follow.actor_id`` and ``Follow.target_id`` from the source model's primary keys
    (typically ``Profile``) to ``DocumentId`` primary keys.

    Rows whose ``actor_id``/``target_id`` cannot be resolved are deleted before the assert,
    matching the policy in the original baseapp_follows 0008 migration.
    """
    Follow = get_apps_model(apps, "baseapp_follows", "Follow")
    SourceModel = get_apps_model(apps, source_app_label, source_model_name)
    DocumentId = apps.get_model("baseapp_core", "DocumentId")
    ContentType = apps.get_model("contenttypes", "ContentType")

    source_ct = ContentType.objects.get(
        app_label=SourceModel._meta.app_label,
        model=SourceModel._meta.model_name,
    )

    doc_by_object_id = {
        doc["object_id"]: doc["id"]
        for doc in DocumentId.objects.filter(content_type_id=source_ct.id).values("id", "object_id")
    }

    for follow in Follow.objects.all():
        actor_doc_id = doc_by_object_id.get(follow.actor_id)
        target_doc_id = doc_by_object_id.get(follow.target_id)
        if actor_doc_id is None or target_doc_id is None:
            Follow.objects.filter(pk=follow.pk).delete()
            continue
        Follow.objects.filter(pk=follow.pk).update(
            actor_id=actor_doc_id,
            target_id=target_doc_id,
        )

    assert_all_follow_rows_reference_document_ids(apps, schema_editor=schema_editor)


def reverse_migrate_follow_document_id_fks_to_profile(
    apps,
    schema_editor,
    *,
    source_app_label: str = "baseapp_profiles",
    source_model_name: str = "Profile",
):
    """
    Restore ``Follow.actor_id`` and ``Follow.target_id`` from ``DocumentId`` primary keys back
    to the source model's primary keys.

    Rows whose ``DocumentId`` does not point at the expected source content type are skipped
    rather than deleted — the reverse path is best-effort and the schema downgrade is what
    actually restores the column type.
    """
    Follow = get_apps_model(apps, "baseapp_follows", "Follow")
    SourceModel = get_apps_model(apps, source_app_label, source_model_name)
    DocumentId = apps.get_model("baseapp_core", "DocumentId")
    ContentType = apps.get_model("contenttypes", "ContentType")

    source_ct = ContentType.objects.get(
        app_label=SourceModel._meta.app_label,
        model=SourceModel._meta.model_name,
    )

    object_id_by_doc = {
        doc["id"]: doc["object_id"]
        for doc in DocumentId.objects.filter(content_type_id=source_ct.id).values("id", "object_id")
    }

    for follow in Follow.objects.all():
        actor_object_id = object_id_by_doc.get(follow.actor_id)
        target_object_id = object_id_by_doc.get(follow.target_id)
        if actor_object_id is None or target_object_id is None:
            continue
        Follow.objects.filter(pk=follow.pk).update(
            actor_id=actor_object_id,
            target_id=target_object_id,
        )
