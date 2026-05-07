"""
Reusable migration helpers to move legacy commentable fields from a model into
`CommentableMetadata` records.

This is useful for legacy projects where models previously inherited a commentable mixin
with concrete columns like `comments_count` and `is_comments_enabled`.

How to use in a migration
-------------------------
1. Ensure your migration depends on the migration that creates `CommentableMetadata`.
2. Before removing old columns from your model, add a `RunPython` operation that calls
   `migrate_legacy_commentable_fields_to_metadata(...)`.
3. Optionally use `reverse_migrate_legacy_commentable_fields_from_metadata(...)` as reverse code.

Example:

    def forwards(apps, schema_editor):
        migrate_legacy_commentable_fields_to_metadata(
            apps,
            schema_editor,
            source_app_label="pages",
            source_model_name="Page",
        )

    def backwards(apps, schema_editor):
        reverse_migrate_legacy_commentable_fields_from_metadata(
            apps,
            schema_editor,
            source_app_label="pages",
            source_model_name="Page",
        )

    migrations.RunPython(forwards, backwards)

Notes
-----
- Missing `DocumentId` rows are created automatically.
- Uses `apps.get_model(...)` exclusively for historical migration safety.
"""


def _alias_pinned_managers(schema_editor, *models):
    # Pin every read/write to the alias the schema editor is operating on so the
    # source-model scan, content-type lookup, DocumentId upserts, and
    # CommentableMetadata writes all hit the same database — same pattern the
    # baseapp_follows migration helpers use.
    if schema_editor is not None and getattr(schema_editor, "connection", None) is not None:
        alias = schema_editor.connection.alias
        return tuple(model.objects.using(alias) for model in models)
    return tuple(model.objects for model in models)


def migrate_legacy_commentable_fields_to_metadata(
    apps,
    schema_editor,
    *,
    source_app_label: str,
    source_model_name: str,
    metadata_app_label: str = "comments",
    metadata_model_name: str = "CommentableMetadata",
    comments_count_field: str = "comments_count",
    is_comments_enabled_field: str = "is_comments_enabled",
):
    SourceModel = apps.get_model(source_app_label, source_model_name)
    ContentType = apps.get_model("contenttypes", "ContentType")
    DocumentId = apps.get_model("baseapp_core", "DocumentId")
    CommentableMetadata = apps.get_model(metadata_app_label, metadata_model_name)
    source_qs, ct_qs, doc_qs, metadata_qs = _alias_pinned_managers(
        schema_editor, SourceModel, ContentType, DocumentId, CommentableMetadata
    )

    legacy_rows = (
        source_qs.exclude(**{f"{comments_count_field}__isnull": True})
        .exclude(**{f"{is_comments_enabled_field}__isnull": True})
        .only("pk", comments_count_field, is_comments_enabled_field)
    )

    if not legacy_rows.exists():
        # Nothing to migrate (fresh DB, e.g. test runner). Bail out before touching
        # ContentType, which is populated by ``post_migrate`` and may not exist yet.
        return

    source_ct, _ = ct_qs.get_or_create(
        app_label=SourceModel._meta.app_label,
        model=SourceModel._meta.model_name,
    )

    for row in legacy_rows:
        doc, _ = doc_qs.get_or_create(
            content_type_id=source_ct.id,
            object_id=row.pk,
        )
        metadata_qs.update_or_create(
            target_id=doc.id,
            defaults={
                "comments_count": getattr(row, comments_count_field),
                "is_comments_enabled": getattr(row, is_comments_enabled_field),
            },
        )


def reverse_migrate_legacy_commentable_fields_from_metadata(
    apps,
    schema_editor,
    *,
    source_app_label: str,
    source_model_name: str,
    metadata_app_label: str = "comments",
    metadata_model_name: str = "CommentableMetadata",
    comments_count_field: str = "comments_count",
    is_comments_enabled_field: str = "is_comments_enabled",
):
    SourceModel = apps.get_model(source_app_label, source_model_name)
    ContentType = apps.get_model("contenttypes", "ContentType")
    CommentableMetadata = apps.get_model(metadata_app_label, metadata_model_name)
    source_qs, ct_qs, metadata_qs = _alias_pinned_managers(
        schema_editor, SourceModel, ContentType, CommentableMetadata
    )

    source_ct = ct_qs.filter(
        app_label=SourceModel._meta.app_label,
        model=SourceModel._meta.model_name,
    ).first()
    if source_ct is None:
        # No ContentType row for the source model (fresh DB / test runner). Nothing
        # to restore.
        return

    metadata_rows = metadata_qs.filter(target__content_type_id=source_ct.id).select_related(
        "target"
    )
    for metadata in metadata_rows:
        source_qs.filter(pk=metadata.target.object_id).update(
            **{
                comments_count_field: metadata.comments_count,
                is_comments_enabled_field: metadata.is_comments_enabled,
            }
        )
