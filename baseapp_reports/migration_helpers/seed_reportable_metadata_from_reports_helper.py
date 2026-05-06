"""
Reusable migration helpers to (re)build ``ReportableMetadata`` rows from existing ``Report``
data.

This is useful right after creating the ``ReportableMetadata`` table for projects that
need their per-target counters seeded from whatever report rows already exist.

How to use in a project migration
---------------------------------
1. Make sure your migration depends on the migration that creates ``ReportableMetadata``.
2. Add a ``RunPython`` operation that calls
   ``seed_reportable_metadata_from_reports(...)``.
3. Use ``reverse_seed_reportable_metadata(...)`` (or
   :func:`migrations.RunPython.noop`) as the reverse code.

Notes
-----
- The helpers resolve models using ``get_apps_model(...)`` so they are safe in
  historical migration state, including when ``Report`` and ``ReportableMetadata`` are
  swapped.
- ``reverse_seed_reportable_metadata`` only deletes rows whose ``target_id`` matches a
  current ``Report.target_object_id`` for the matching content type, so unrelated
  metadata records are preserved.
"""

from baseapp_core.swapper import get_apps_model


def _default_reports_count():
    return {"total": 0}


def seed_reportable_metadata_from_reports(
    apps,
    schema_editor,
    *,
    metadata_app_label: str = "baseapp_reports",
    metadata_model_name: str = "ReportableMetadata",
):
    """
    Create or update one ``ReportableMetadata`` row per ``DocumentId`` that has any
    ``Report`` rows pointing at it, populating ``reports_count`` from a fresh count of
    the live report data.
    """
    Report = get_apps_model(apps, "baseapp_reports", "Report")
    ReportType = get_apps_model(apps, "baseapp_reports", "ReportType")
    ReportableMetadata = get_apps_model(apps, metadata_app_label, metadata_model_name)
    DocumentId = apps.get_model("baseapp_core", "DocumentId")

    target_pairs = (
        Report.objects.exclude(target_content_type__isnull=True)
        .exclude(target_object_id__isnull=True)
        .values_list("target_content_type_id", "target_object_id")
        .distinct()
    )

    type_keys = list(ReportType.objects.values_list("id", "key"))

    for ct_id, obj_id in target_pairs:
        doc, _ = DocumentId.objects.get_or_create(content_type_id=ct_id, object_id=obj_id)
        counts = _default_reports_count()
        for type_id, key in type_keys:
            counts[key] = Report.objects.filter(
                target_content_type_id=ct_id,
                target_object_id=obj_id,
                report_type_id=type_id,
            ).count()
            counts["total"] += counts[key]
        ReportableMetadata.objects.update_or_create(
            target_id=doc.id,
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
    Drop ``ReportableMetadata`` rows that were seeded from existing ``Report`` data.

    Only rows whose ``target_id`` references a ``DocumentId`` currently used by a live
    ``Report`` are removed; unrelated metadata rows are left untouched.
    """
    Report = get_apps_model(apps, "baseapp_reports", "Report")
    ReportableMetadata = get_apps_model(apps, metadata_app_label, metadata_model_name)
    DocumentId = apps.get_model("baseapp_core", "DocumentId")

    pairs = (
        Report.objects.exclude(target_content_type__isnull=True)
        .exclude(target_object_id__isnull=True)
        .values_list("target_content_type_id", "target_object_id")
        .distinct()
    )

    doc_ids = list(
        DocumentId.objects.filter(
            content_type_id__in=[ct for ct, _ in pairs],
            object_id__in=[obj for _, obj in pairs],
        ).values_list("id", flat=True)
    )

    if doc_ids:
        ReportableMetadata.objects.filter(target_id__in=doc_ids).delete()
