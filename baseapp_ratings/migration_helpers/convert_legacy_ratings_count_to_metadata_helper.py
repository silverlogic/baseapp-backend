"""
Reusable migration helpers to move legacy ratings columns from a model into
`RatableMetadata` records.

Useful for legacy projects whose models previously inherited
`baseapp_ratings.models.RatableModel` (now removed) and therefore carried
`ratings_count` / `ratings_sum` / `ratings_average` / `is_ratings_enabled`
columns directly.

How to use in a migration
-------------------------
1. Ensure your migration depends on the migration that creates `RatableMetadata`.
2. Before removing the legacy columns from your model, add a `RunPython` operation
   that calls `migrate_legacy_ratings_to_metadata(...)`.
3. Optionally use `reverse_migrate_legacy_ratings_from_metadata(...)` as the
   reverse code.

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


def migrate_legacy_ratings_to_metadata(
    apps,
    schema_editor,
    *,
    source_app_label: str,
    source_model_name: str,
    metadata_app_label: str = "baseapp_ratings",
    metadata_model_name: str = "RatableMetadata",
    ratings_count_field: str = "ratings_count",
    ratings_sum_field: str = "ratings_sum",
    ratings_average_field: str = "ratings_average",
    is_ratings_enabled_field: str = "is_ratings_enabled",
):
    SourceModel = apps.get_model(source_app_label, source_model_name)
    ContentType = apps.get_model("contenttypes", "ContentType")
    DocumentId = apps.get_model("baseapp_core", "DocumentId")
    RatableMetadata = apps.get_model(metadata_app_label, metadata_model_name)
    source_qs, ct_qs, doc_qs, metadata_qs = _alias_pinned_managers(
        schema_editor, SourceModel, ContentType, DocumentId, RatableMetadata
    )

    legacy_rows = source_qs.only(
        "pk",
        ratings_count_field,
        ratings_sum_field,
        ratings_average_field,
        is_ratings_enabled_field,
    )

    if not legacy_rows.exists():
        # Fresh DB / test runner: nothing to migrate. Bail out before touching
        # ContentType, which is populated by `post_migrate` and may not exist yet.
        return

    source_ct, _ = ct_qs.get_or_create(
        app_label=SourceModel._meta.app_label,
        model=SourceModel._meta.model_name,
    )

    for row in legacy_rows:
        doc, _ = doc_qs.get_or_create(content_type_id=source_ct.id, object_id=row.pk)
        metadata_qs.update_or_create(
            target_id=doc.id,
            defaults={
                "ratings_count": getattr(row, ratings_count_field) or 0,
                "ratings_sum": getattr(row, ratings_sum_field) or 0,
                "ratings_average": getattr(row, ratings_average_field) or 0,
                "is_ratings_enabled": bool(getattr(row, is_ratings_enabled_field, True)),
            },
        )


def reverse_migrate_legacy_ratings_from_metadata(
    apps,
    schema_editor,
    *,
    source_app_label: str,
    source_model_name: str,
    metadata_app_label: str = "baseapp_ratings",
    metadata_model_name: str = "RatableMetadata",
    ratings_count_field: str = "ratings_count",
    ratings_sum_field: str = "ratings_sum",
    ratings_average_field: str = "ratings_average",
    is_ratings_enabled_field: str = "is_ratings_enabled",
):
    SourceModel = apps.get_model(source_app_label, source_model_name)
    ContentType = apps.get_model("contenttypes", "ContentType")
    RatableMetadata = apps.get_model(metadata_app_label, metadata_model_name)
    source_qs, ct_qs, metadata_qs = _alias_pinned_managers(
        schema_editor, SourceModel, ContentType, RatableMetadata
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
                ratings_count_field: metadata.ratings_count,
                ratings_sum_field: metadata.ratings_sum,
                ratings_average_field: metadata.ratings_average,
                is_ratings_enabled_field: metadata.is_ratings_enabled,
            }
        )
