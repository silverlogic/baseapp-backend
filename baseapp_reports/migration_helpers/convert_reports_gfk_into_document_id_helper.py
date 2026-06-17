"""
Reusable migration helpers to convert report targets from GenericForeignKey columns
(`target_content_type`, `target_object_id`) to a `DocumentId` foreign key (`target_document`).

Mirrors `baseapp_comments.migration_helpers.convert_comments_gfk_into_document_id_helper`:
the helper backfills `Report.target_document` from the legacy GFK columns, creating
`DocumentId` rows for any (content_type, object_id) pair that doesn't have one yet, and
asserts every Report row has a non-null `target_document` at the end so the project
migration can safely tighten the column to NOT NULL.

How to use in a project migration
---------------------------------
1. Add `target_document` to your project's Report model (nullable initially).
2. Import these functions:

   from baseapp_reports.migration_helpers.convert_reports_gfk_into_document_id_helper import (
       migrate_report_targets_to_document_id,
       reverse_migrate_report_targets_to_generic_fk,
   )

3. Add a `migrations.RunPython(...)` operation BEFORE removing the legacy GFK columns:

   migrations.RunPython(
       migrate_report_targets_to_document_id,
       reverse_migrate_report_targets_to_generic_fk,
   )

4. Run `migrations.AlterField` to set `target_document` to `null=False` AFTER the backfill.

5. Remove `target_content_type` and `target_object_id` fields, plus the matching
   `unique_together` / `Index`.

Notes
-----
- The helpers resolve models using `apps.get_model(...)` so they are safe in historical
  migration state.
- Missing `DocumentId` rows are created automatically. If a report references a missing
  `ContentType` (e.g. orphaned `target_content_type_id`), `DocumentId.objects.create`
  can raise `IntegrityError` — fix or remove bad rows in advance.
- Pins every read/write to `schema_editor.connection.alias` so all the traffic hits
  the same database.
"""

from baseapp_core.swapper import get_apps_model


def _alias_pinned_managers(schema_editor, *models):
    if schema_editor is not None and getattr(schema_editor, "connection", None) is not None:
        alias = schema_editor.connection.alias
        return tuple(model.objects.using(alias) for model in models)
    return tuple(model.objects for model in models)


def assert_all_report_rows_have_target_document(apps, schema_editor=None) -> None:
    """
    Fail if any `Report` row has `target_document_id` NULL. Call after
    :func:`migrate_report_targets_to_document_id` when the schema is about to enforce
    `null=False` on `Report.target_document`.

    The forward :func:`migrate_report_targets_to_document_id` also invokes this at the
    end so a project migration does not need a separate `RunPython` for the check.
    """
    Report = get_apps_model(apps, "baseapp_reports", "Report")
    (report_qs,) = _alias_pinned_managers(schema_editor, Report)
    n = report_qs.filter(target_document_id__isnull=True).count()
    if n:
        raise ValueError(
            f"Reports GFK migration: {n} row(s) still have target_document_id NULL after "
            "backfill. Cannot set Report.target_document to NOT NULL until resolved."
        )


def migrate_report_targets_to_document_id(apps, schema_editor):
    Report = get_apps_model(apps, "baseapp_reports", "Report")
    DocumentId = apps.get_model("baseapp_core", "DocumentId")
    report_qs, doc_qs = _alias_pinned_managers(schema_editor, Report, DocumentId)

    if not report_qs.exists():
        # Fresh DB (e.g. test runner). Nothing to backfill — just no-op the assertion.
        return

    doc_map = {
        (doc["content_type_id"], doc["object_id"]): doc["id"]
        for doc in doc_qs.values("id", "content_type_id", "object_id")
    }

    target_pairs = (
        report_qs.exclude(target_content_type_id__isnull=True)
        .exclude(target_object_id__isnull=True)
        .values_list("target_content_type_id", "target_object_id")
        .distinct()
    )
    for content_type_id, object_id in target_pairs:
        key = (content_type_id, object_id)
        if key not in doc_map:
            # Bad FK to django_content_type raises IntegrityError and stops migrate.
            doc = doc_qs.create(content_type_id=content_type_id, object_id=object_id)
            doc_map[key] = doc.id

    for report in report_qs.filter(target_document_id__isnull=True).exclude(
        target_content_type_id__isnull=True
    ):
        key = (report.target_content_type_id, report.target_object_id)
        document_id = doc_map.get(key)
        if document_id:
            report_qs.filter(pk=report.pk).update(target_document_id=document_id)

    assert_all_report_rows_have_target_document(apps, schema_editor=schema_editor)


def reverse_migrate_report_targets_to_generic_fk(apps, schema_editor):
    Report = get_apps_model(apps, "baseapp_reports", "Report")
    (report_qs,) = _alias_pinned_managers(schema_editor, Report)

    for report in report_qs.filter(target_document_id__isnull=False).select_related(
        "target_document"
    ):
        report_qs.filter(pk=report.pk).update(
            target_content_type_id=report.target_document.content_type_id,
            target_object_id=report.target_document.object_id,
        )
