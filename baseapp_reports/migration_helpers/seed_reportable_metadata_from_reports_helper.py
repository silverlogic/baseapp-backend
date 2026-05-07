"""
Reusable migration helpers to (re)build `ReportableMetadata` rows from existing `Report`
data.

This is useful right after creating the `ReportableMetadata` table for projects that
need their per-target counters seeded from whatever report rows already exist.

How to use in a project migration
---------------------------------
1. Make sure your migration depends on the migration that creates `ReportableMetadata`.
2. Add a `RunPython` operation that calls
   `seed_reportable_metadata_from_reports(...)`.
3. Use `reverse_seed_reportable_metadata(...)` (or
   :func:`migrations.RunPython.noop`) as the reverse code.

Notes
-----
- The helpers resolve models using `get_apps_model(...)` so they are safe in
  historical migration state, including when `Report` and `ReportableMetadata` are
  swapped.
- `reverse_seed_reportable_metadata` only deletes rows whose `target_id` matches a
  current `Report.target_object_id` for the matching content type, so unrelated
  metadata records are preserved.
- Pins every read/write to `schema_editor.connection.alias` so the
  `Report`/`ReportType`/`DocumentId`/`ReportableMetadata` traffic all hits the
  same database — same pattern the baseapp_follows / baseapp_comments helpers use.
"""

from baseapp_core.swapper import get_apps_model


def _default_reports_count():
    return {"total": 0}


def _alias_pinned_managers(schema_editor, *models):
    if schema_editor is not None and getattr(schema_editor, "connection", None) is not None:
        alias = schema_editor.connection.alias
        return tuple(model.objects.using(alias) for model in models)
    return tuple(model.objects for model in models)


def seed_reportable_metadata_from_reports(
    apps,
    schema_editor,
    *,
    metadata_app_label: str = "baseapp_reports",
    metadata_model_name: str = "ReportableMetadata",
):
    """
    Create or update one `ReportableMetadata` row per `DocumentId` that has any
    `Report` rows pointing at it, populating `reports_count` from a fresh count of
    the live report data.
    """
    Report = get_apps_model(apps, "baseapp_reports", "Report")
    ReportType = get_apps_model(apps, "baseapp_reports", "ReportType")
    ReportableMetadata = get_apps_model(apps, metadata_app_label, metadata_model_name)
    report_qs, report_type_qs, metadata_qs = _alias_pinned_managers(
        schema_editor, Report, ReportType, ReportableMetadata
    )

    target_doc_ids = list(
        report_qs.exclude(target_document__isnull=True)
        .values_list("target_document_id", flat=True)
        .distinct()
    )

    type_keys = list(report_type_qs.values_list("id", "key"))

    for doc_id in target_doc_ids:
        counts = _default_reports_count()
        for type_id, key in type_keys:
            counts[key] = report_qs.filter(
                target_document_id=doc_id,
                report_type_id=type_id,
            ).count()
            counts["total"] += counts[key]
        metadata_qs.update_or_create(
            target_id=doc_id,
            defaults={"reports_count": counts},
        )


def reverse_seed_reportable_metadata(
    apps,
    schema_editor,
    *,
    metadata_app_label: str = "baseapp_reports",
    metadata_model_name: str = "ReportableMetadata",
):
    """
    Drop `ReportableMetadata` rows that were seeded from existing `Report` data.

    Only rows whose `target_id` references a `DocumentId` currently used by a live
    `Report` are removed; unrelated metadata rows are left untouched.
    """
    Report = get_apps_model(apps, "baseapp_reports", "Report")
    ReportableMetadata = get_apps_model(apps, metadata_app_label, metadata_model_name)
    report_qs, metadata_qs = _alias_pinned_managers(schema_editor, Report, ReportableMetadata)

    doc_ids = list(
        report_qs.exclude(target_document__isnull=True)
        .values_list("target_document_id", flat=True)
        .distinct()
    )

    if doc_ids:
        metadata_qs.filter(target_id__in=doc_ids).delete()
