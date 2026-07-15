"""
Reusable migration helpers to (re)build `RatableMetadata` rows from existing `Rate`
data.

This is useful right after creating the `RatableMetadata` table for projects that
need their per-target counters seeded from whatever rate rows already exist.

How to use in a project migration
---------------------------------
1. Make sure your migration depends on the migration that creates `RatableMetadata`.
2. Add a `RunPython` operation that calls `seed_ratable_metadata_from_rates(...)`.
3. Use `reverse_seed_ratable_metadata(...)` (or :func:`migrations.RunPython.noop`)
   as the reverse code.

Notes
-----
- Resolves models via `get_apps_model(...)` so it's safe in historical migration
  state, including when `Rate` / `RatableMetadata` are swapped.
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


def seed_ratable_metadata_from_rates(
    apps,
    schema_editor,
    *,
    metadata_app_label: str = "baseapp_ratings",
    metadata_model_name: str = "RatableMetadata",
) -> None:
    """
    Create or update one `RatableMetadata` row per `DocumentId` referenced as a
    `Rate.target_document`, populating count / sum / average from a fresh aggregate.
    """
    Rate = get_apps_model(apps, "baseapp_ratings", "Rate")
    RatableMetadata = get_apps_model(apps, metadata_app_label, metadata_model_name)
    rate_qs, metadata_qs = _alias_pinned_managers(schema_editor, Rate, RatableMetadata)

    target_doc_ids = list(
        rate_qs.exclude(target_document__isnull=True)
        .values_list("target_document_id", flat=True)
        .distinct()
    )

    for doc_id in target_doc_ids:
        rates_for_target = rate_qs.filter(target_document_id=doc_id)
        count = rates_for_target.count()
        total = sum(rates_for_target.values_list("value", flat=True)) or 0
        average = (total / count) if count else 0
        metadata_qs.update_or_create(
            target_id=doc_id,
            defaults={
                "ratings_count": count,
                "ratings_sum": total,
                "ratings_average": average,
            },
        )


def reverse_seed_ratable_metadata(
    apps,
    schema_editor,
    *,
    metadata_app_label: str = "baseapp_ratings",
    metadata_model_name: str = "RatableMetadata",
) -> None:
    """
    Drop `RatableMetadata` rows that were seeded from existing `Rate` data. Only
    rows whose `target_id` is referenced as a live `Rate.target_document` are
    removed; unrelated metadata records are left untouched.
    """
    Rate = get_apps_model(apps, "baseapp_ratings", "Rate")
    RatableMetadata = get_apps_model(apps, metadata_app_label, metadata_model_name)
    rate_qs, metadata_qs = _alias_pinned_managers(schema_editor, Rate, RatableMetadata)

    doc_ids = list(
        rate_qs.exclude(target_document__isnull=True)
        .values_list("target_document_id", flat=True)
        .distinct()
    )

    if doc_ids:
        metadata_qs.filter(target_id__in=doc_ids).delete()
