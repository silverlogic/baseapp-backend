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

    source_ct = ContentType.objects.get(
        app_label=SourceModel._meta.app_label,
        model=SourceModel._meta.model_name,
    )

    legacy_rows = (
        SourceModel.objects.exclude(**{f"{comments_count_field}__isnull": True})
        .exclude(**{f"{is_comments_enabled_field}__isnull": True})
        .only("pk", comments_count_field, is_comments_enabled_field)
    )

    for row in legacy_rows:
        doc, _ = DocumentId.objects.get_or_create(
            content_type_id=source_ct.id,
            object_id=row.pk,
        )
        CommentableMetadata.objects.update_or_create(
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

    source_ct = ContentType.objects.get(
        app_label=SourceModel._meta.app_label,
        model=SourceModel._meta.model_name,
    )

    metadata_rows = CommentableMetadata.objects.filter(
        target__content_type_id=source_ct.id
    ).select_related("target")
    for metadata in metadata_rows:
        SourceModel.objects.filter(pk=metadata.target.object_id).update(
            **{
                comments_count_field: metadata.comments_count,
                is_comments_enabled_field: metadata.is_comments_enabled,
            }
        )
