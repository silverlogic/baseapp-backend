"""
Reusable migration helpers to move legacy `blockers_count` / `blocking_count`
PositiveIntegerField data from a model (typically `Profile`) into
`BlockableMetadata` records.

Useful for legacy projects whose models previously inherited
`baseapp_blocks.models.BlockableModel` and therefore carried concrete
`blockers_count` / `blocking_count` columns.

How to use in a migration
-------------------------
1. Ensure your migration depends on the migration that creates `BlockableMetadata`.
2. Before removing the old columns from your model, add a `RunPython` operation
   that calls `migrate_legacy_block_counts_to_metadata(...)`.
3. Optionally use `reverse_migrate_legacy_block_counts_from_metadata(...)` as
   the reverse code.

Notes
-----
- Missing `DocumentId` rows are created automatically.
- Uses `apps.get_model(...)` exclusively for historical migration safety.
- Pins reads/writes to `schema_editor.connection.alias`.
- Early-returns if the source table is empty so the helper is safe on a fresh
  test DB where `post_migrate` hasn't populated ContentType yet.
"""


def _alias_pinned_managers(schema_editor, *models):
    if schema_editor is not None and getattr(schema_editor, "connection", None) is not None:
        alias = schema_editor.connection.alias
        return tuple(model.objects.using(alias) for model in models)
    return tuple(model.objects for model in models)


def migrate_legacy_block_counts_to_metadata(
    apps,
    schema_editor,
    *,
    source_app_label: str,
    source_model_name: str,
    metadata_app_label: str = "baseapp_blocks",
    metadata_model_name: str = "BlockableMetadata",
    blockers_count_field: str = "blockers_count",
    blocking_count_field: str = "blocking_count",
):
    SourceModel = apps.get_model(source_app_label, source_model_name)
    ContentType = apps.get_model("contenttypes", "ContentType")
    DocumentId = apps.get_model("baseapp_core", "DocumentId")
    BlockableMetadata = apps.get_model(metadata_app_label, metadata_model_name)
    source_qs, ct_qs, doc_qs, metadata_qs = _alias_pinned_managers(
        schema_editor, SourceModel, ContentType, DocumentId, BlockableMetadata
    )

    legacy_rows = source_qs.only("pk", blockers_count_field, blocking_count_field)
    if not legacy_rows.exists():
        # Fresh DB / test runner: nothing to migrate. Bail before touching
        # ContentType (populated by post_migrate, may not exist yet).
        return

    source_ct, _ = ct_qs.get_or_create(
        app_label=SourceModel._meta.app_label,
        model=SourceModel._meta.model_name,
    )

    for row in legacy_rows:
        defaults = {}
        blockers_count = getattr(row, blockers_count_field, None)
        if blockers_count is not None:
            defaults["blockers_count"] = int(blockers_count)
        blocking_count = getattr(row, blocking_count_field, None)
        if blocking_count is not None:
            defaults["blocking_count"] = int(blocking_count)

        if not defaults:
            continue

        doc, _ = doc_qs.get_or_create(
            content_type_id=source_ct.id,
            object_id=row.pk,
        )
        metadata_qs.update_or_create(target_id=doc.id, defaults=defaults)


def reverse_migrate_legacy_block_counts_from_metadata(
    apps,
    schema_editor,
    *,
    source_app_label: str,
    source_model_name: str,
    metadata_app_label: str = "baseapp_blocks",
    metadata_model_name: str = "BlockableMetadata",
    blockers_count_field: str = "blockers_count",
    blocking_count_field: str = "blocking_count",
):
    SourceModel = apps.get_model(source_app_label, source_model_name)
    ContentType = apps.get_model("contenttypes", "ContentType")
    BlockableMetadata = apps.get_model(metadata_app_label, metadata_model_name)
    source_qs, ct_qs, metadata_qs = _alias_pinned_managers(
        schema_editor, SourceModel, ContentType, BlockableMetadata
    )

    source_ct = ct_qs.filter(
        app_label=SourceModel._meta.app_label,
        model=SourceModel._meta.model_name,
    ).first()
    if source_ct is None:
        return

    metadata_rows = metadata_qs.filter(target__content_type_id=source_ct.id).select_related(
        "target"
    )
    for metadata in metadata_rows:
        source_qs.filter(pk=metadata.target.object_id).update(
            **{
                blockers_count_field: metadata.blockers_count,
                blocking_count_field: metadata.blocking_count,
            }
        )
