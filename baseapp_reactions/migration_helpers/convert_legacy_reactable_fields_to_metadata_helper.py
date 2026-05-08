"""
Reusable migration helpers to move legacy `reactions_count` JSONField and
`is_reactions_enabled` Boolean data from a model into `ReactableMetadata`
records.

Useful for legacy projects whose models previously inherited
`baseapp_reactions.models.ReactableModel` and therefore carried concrete
`reactions_count` / `is_reactions_enabled` columns.

How to use in a migration
-------------------------
1. Ensure your migration depends on the migration that creates `ReactableMetadata`.
2. Before removing the old columns from your model, add a `RunPython` operation
   that calls `migrate_legacy_reactable_fields_to_metadata(...)`.
3. Optionally use `reverse_migrate_legacy_reactable_fields_from_metadata(...)`
   as the reverse code.

Notes
-----
- Missing `DocumentId` rows are created automatically.
- Uses `apps.get_model(...)` exclusively for historical migration safety.
- Pins reads/writes to `schema_editor.connection.alias`.
"""


def _alias_pinned_managers(schema_editor, *models):
    if schema_editor is not None and getattr(schema_editor, "connection", None) is not None:
        alias = schema_editor.connection.alias
        return tuple(model.objects.using(alias) for model in models)
    return tuple(model.objects for model in models)


def migrate_legacy_reactable_fields_to_metadata(
    apps,
    schema_editor,
    *,
    source_app_label: str,
    source_model_name: str,
    metadata_app_label: str = "baseapp_reactions",
    metadata_model_name: str = "ReactableMetadata",
    reactions_count_field: str = "reactions_count",
    is_reactions_enabled_field: str = "is_reactions_enabled",
):
    SourceModel = apps.get_model(source_app_label, source_model_name)
    ContentType = apps.get_model("contenttypes", "ContentType")
    DocumentId = apps.get_model("baseapp_core", "DocumentId")
    ReactableMetadata = apps.get_model(metadata_app_label, metadata_model_name)
    source_qs, ct_qs, doc_qs, metadata_qs = _alias_pinned_managers(
        schema_editor, SourceModel, ContentType, DocumentId, ReactableMetadata
    )

    # `get_or_create` so the helper is self-sufficient on a fresh DB (e.g. test
    # runner) where `post_migrate` hasn't yet populated the ContentType row.
    source_ct, _ = ct_qs.get_or_create(
        app_label=SourceModel._meta.app_label,
        model=SourceModel._meta.model_name,
    )

    legacy_rows = source_qs.only("pk", reactions_count_field, is_reactions_enabled_field)

    for row in legacy_rows:
        doc, _ = doc_qs.get_or_create(
            content_type_id=source_ct.id,
            object_id=row.pk,
        )
        defaults = {}
        reactions_count = getattr(row, reactions_count_field, None)
        if reactions_count is not None:
            defaults["reactions_count"] = reactions_count
        is_reactions_enabled = getattr(row, is_reactions_enabled_field, None)
        if is_reactions_enabled is not None:
            defaults["is_reactions_enabled"] = bool(is_reactions_enabled)
        metadata_qs.update_or_create(target_id=doc.id, defaults=defaults)


def reverse_migrate_legacy_reactable_fields_from_metadata(
    apps,
    schema_editor,
    *,
    source_app_label: str,
    source_model_name: str,
    metadata_app_label: str = "baseapp_reactions",
    metadata_model_name: str = "ReactableMetadata",
    reactions_count_field: str = "reactions_count",
    is_reactions_enabled_field: str = "is_reactions_enabled",
):
    SourceModel = apps.get_model(source_app_label, source_model_name)
    ContentType = apps.get_model("contenttypes", "ContentType")
    ReactableMetadata = apps.get_model(metadata_app_label, metadata_model_name)
    source_qs, ct_qs, metadata_qs = _alias_pinned_managers(
        schema_editor, SourceModel, ContentType, ReactableMetadata
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
                reactions_count_field: metadata.reactions_count,
                is_reactions_enabled_field: metadata.is_reactions_enabled,
            }
        )
