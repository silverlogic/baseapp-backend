"""
Reusable migration helpers to convert `Rate` targets from GenericForeignKey columns
(`target_content_type`, `target_object_id`) to a `DocumentId` foreign key
(`target_document`).

Mirrors `baseapp_reports.migration_helpers.convert_reports_gfk_into_document_id_helper`.

How to use in a project migration
---------------------------------
1. Add `target_document` to your project's Rate model (nullable initially).
2. Import these functions:

   from baseapp_ratings.migration_helpers.convert_rates_gfk_into_document_id_helper import (
       migrate_rate_targets_to_document_id,
       reverse_migrate_rate_targets_to_generic_fk,
   )

3. Add a `migrations.RunPython(...)` BEFORE removing the legacy GFK columns.

4. Run `migrations.AlterField` to set `target_document` to `null=False` AFTER
   the backfill.

5. Remove `target_content_type` and `target_object_id` fields, plus the matching
   `unique_together` / index, then re-add the new `unique_together` /
   index keyed on `target_document`.

Notes
-----
- Resolves models via `apps.get_model(...)` for historical safety.
- Missing `DocumentId` rows are created automatically.
- Pins reads/writes to `schema_editor.connection.alias`.
"""

from typing import TYPE_CHECKING

from baseapp_core.swapper import get_apps_model

if TYPE_CHECKING:
    from django.db.models import Manager, QuerySet


def _alias_pinned_managers(schema_editor, *models) -> "tuple[Manager | QuerySet, ...]":
    if schema_editor is not None and getattr(schema_editor, "connection", None) is not None:
        alias = schema_editor.connection.alias
        return tuple(model.objects.using(alias) for model in models)
    return tuple(model.objects for model in models)


def assert_all_rate_rows_have_target_document(apps, schema_editor=None) -> None:
    """Fail if any `Rate` row has `target_document_id` NULL after the backfill."""
    Rate = get_apps_model(apps, "baseapp_ratings", "Rate")
    (rate_qs,) = _alias_pinned_managers(schema_editor, Rate)
    n = rate_qs.filter(target_document_id__isnull=True).count()
    if n:
        raise ValueError(
            f"Ratings GFK migration: {n} row(s) still have target_document_id NULL after "
            "backfill. Cannot set Rate.target_document to NOT NULL until resolved."
        )


def migrate_rate_targets_to_document_id(apps, schema_editor) -> None:
    Rate = get_apps_model(apps, "baseapp_ratings", "Rate")
    DocumentId = apps.get_model("baseapp_core", "DocumentId")
    rate_qs, doc_qs = _alias_pinned_managers(schema_editor, Rate, DocumentId)

    if not rate_qs.exists():
        # Fresh DB / test runner. Nothing to backfill.
        return

    doc_map = {
        (doc["content_type_id"], doc["object_id"]): doc["id"]
        for doc in doc_qs.values("id", "content_type_id", "object_id")
    }

    target_pairs = (
        rate_qs.exclude(target_content_type_id__isnull=True)
        .exclude(target_object_id__isnull=True)
        .values_list("target_content_type_id", "target_object_id")
        .distinct()
    )
    for content_type_id, object_id in target_pairs:
        key = (content_type_id, object_id)
        if key not in doc_map:
            doc = doc_qs.create(content_type_id=content_type_id, object_id=object_id)
            doc_map[key] = doc.id

    for rate in rate_qs.filter(target_document_id__isnull=True).exclude(
        target_content_type_id__isnull=True
    ):
        key = (rate.target_content_type_id, rate.target_object_id)
        document_id = doc_map.get(key)
        if document_id:
            rate_qs.filter(pk=rate.pk).update(target_document_id=document_id)

    assert_all_rate_rows_have_target_document(apps, schema_editor=schema_editor)


def reverse_migrate_rate_targets_to_generic_fk(apps, schema_editor) -> None:
    Rate = get_apps_model(apps, "baseapp_ratings", "Rate")
    (rate_qs,) = _alias_pinned_managers(schema_editor, Rate)

    for rate in rate_qs.filter(target_document_id__isnull=False).select_related("target_document"):
        rate_qs.filter(pk=rate.pk).update(
            target_content_type_id=rate.target_document.content_type_id,
            target_object_id=rate.target_document.object_id,
        )
