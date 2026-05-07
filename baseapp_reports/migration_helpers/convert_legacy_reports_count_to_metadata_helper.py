"""
Reusable migration helpers to move legacy `reports_count` JSONField data from a model
into `ReportableMetadata` records.

This is useful for legacy projects where models previously inherited
`baseapp_reports.models.ReportableModel` (now removed) and therefore carried a
concrete `reports_count` JSONField column.

How to use in a migration
-------------------------
1. Ensure your migration depends on the migration that creates `ReportableMetadata`.
2. Before removing the old column from your model, add a `RunPython` operation that
   calls `migrate_legacy_reports_count_to_metadata(...)`.
3. Optionally use `reverse_migrate_legacy_reports_count_from_metadata(...)` as
   reverse code.

Notes
-----
- Missing `DocumentId` rows are created automatically.
- Uses `apps.get_model(...)` exclusively for historical migration safety.
- Pins every read/write to `schema_editor.connection.alias` so the source-row scan,
  ContentType / DocumentId lookups, and `ReportableMetadata` writes all hit the same
  database — same pattern the baseapp_follows / baseapp_comments helpers use.
"""


def _alias_pinned_managers(schema_editor, *models):
    # Pin every read/write to the alias the schema editor is operating on so the
    # source-model scan, content-type lookup, DocumentId upserts, and
    # ReportableMetadata writes all hit the same database — same pattern the
    # baseapp_follows / baseapp_comments migration helpers use.
    if schema_editor is not None and getattr(schema_editor, "connection", None) is not None:
        alias = schema_editor.connection.alias
        return tuple(model.objects.using(alias) for model in models)
    return tuple(model.objects for model in models)


def migrate_legacy_reports_count_to_metadata(
    apps,
    schema_editor,
    *,
    source_app_label: str,
    source_model_name: str,
    metadata_app_label: str = "baseapp_reports",
    metadata_model_name: str = "ReportableMetadata",
    reports_count_field: str = "reports_count",
):
    SourceModel = apps.get_model(source_app_label, source_model_name)
    ContentType = apps.get_model("contenttypes", "ContentType")
    DocumentId = apps.get_model("baseapp_core", "DocumentId")
    ReportableMetadata = apps.get_model(metadata_app_label, metadata_model_name)
    source_qs, ct_qs, doc_qs, metadata_qs = _alias_pinned_managers(
        schema_editor, SourceModel, ContentType, DocumentId, ReportableMetadata
    )

    # `get_or_create` so the helper is self-sufficient on a fresh DB (e.g. test runner)
    # where `post_migrate` hasn't yet populated the ContentType row for this model.
    source_ct, _ = ct_qs.get_or_create(
        app_label=SourceModel._meta.app_label,
        model=SourceModel._meta.model_name,
    )

    legacy_rows = source_qs.exclude(**{f"{reports_count_field}__isnull": True}).only(
        "pk", reports_count_field
    )

    for row in legacy_rows:
        doc, _ = doc_qs.get_or_create(
            content_type_id=source_ct.id,
            object_id=row.pk,
        )
        metadata_qs.update_or_create(
            target_id=doc.id,
            defaults={
                "reports_count": getattr(row, reports_count_field),
            },
        )


def reverse_migrate_legacy_reports_count_from_metadata(
    apps,
    schema_editor,
    *,
    source_app_label: str,
    source_model_name: str,
    metadata_app_label: str = "baseapp_reports",
    metadata_model_name: str = "ReportableMetadata",
    reports_count_field: str = "reports_count",
):
    SourceModel = apps.get_model(source_app_label, source_model_name)
    ContentType = apps.get_model("contenttypes", "ContentType")
    ReportableMetadata = apps.get_model(metadata_app_label, metadata_model_name)
    source_qs, ct_qs, metadata_qs = _alias_pinned_managers(
        schema_editor, SourceModel, ContentType, ReportableMetadata
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
            **{reports_count_field: metadata.reports_count}
        )
