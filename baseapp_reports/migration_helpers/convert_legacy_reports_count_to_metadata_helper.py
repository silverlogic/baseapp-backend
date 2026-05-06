"""
Reusable migration helpers to move legacy ``reports_count`` JSONField data from a model
into ``ReportableMetadata`` records.

This is useful for legacy projects where models previously inherited
``baseapp_reports.models.ReportableModel`` (now removed) and therefore carried a
concrete ``reports_count`` JSONField column.

How to use in a migration
-------------------------
1. Ensure your migration depends on the migration that creates ``ReportableMetadata``.
2. Before removing the old column from your model, add a ``RunPython`` operation that
   calls ``migrate_legacy_reports_count_to_metadata(...)``.
3. Optionally use ``reverse_migrate_legacy_reports_count_from_metadata(...)`` as
   reverse code.

Notes
-----
- Missing ``DocumentId`` rows are created automatically.
- Uses ``apps.get_model(...)`` exclusively for historical migration safety.
"""


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

    legacy_rows = SourceModel.objects.exclude(**{f"{reports_count_field}__isnull": True}).only(
        "pk", reports_count_field
    )

    if not legacy_rows.exists():
        # Nothing to migrate (fresh DB, e.g. test runner). Bail out before touching
        # ContentType, which is populated by ``post_migrate`` and may not exist yet.
        return

    source_ct, _ = ContentType.objects.get_or_create(
        app_label=SourceModel._meta.app_label,
        model=SourceModel._meta.model_name,
    )

    for row in legacy_rows:
        doc, _ = DocumentId.objects.get_or_create(
            content_type_id=source_ct.id,
            object_id=row.pk,
        )
        ReportableMetadata.objects.update_or_create(
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

    source_ct = ContentType.objects.filter(
        app_label=SourceModel._meta.app_label,
        model=SourceModel._meta.model_name,
    ).first()
    if source_ct is None:
        return

    metadata_rows = ReportableMetadata.objects.filter(
        target__content_type_id=source_ct.id
    ).select_related("target")
    for metadata in metadata_rows:
        SourceModel.objects.filter(pk=metadata.target.object_id).update(
            **{reports_count_field: metadata.reports_count}
        )
