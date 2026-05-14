"""
Reusable migration helpers to (re)build `ReactableMetadata` rows from existing
`Reaction` data.

Useful right after creating the `ReactableMetadata` table for projects that need
their per-target reaction counters seeded from whatever reaction rows already exist.

How to use in a project migration
---------------------------------
1. Make sure your migration depends on the migration that creates `ReactableMetadata`.
2. Add a `RunPython` operation that calls `seed_reactable_metadata_from_reactions(...)`.
3. Use `reverse_seed_reactable_metadata(...)` (or :func:`migrations.RunPython.noop`)
   as the reverse code.

Notes
-----
- Resolves models via `get_apps_model(...)` so it's safe in historical migration
  state, including when `Reaction` / `ReactableMetadata` are swapped.
- Pins reads/writes to `schema_editor.connection.alias`.
- `is_reactions_enabled` is left at its model default — `Reaction` rows don't
  carry that flag, so this seeder only populates the per-type counts dict.
"""

from baseapp_core.swapper import get_apps_model


def _alias_pinned_managers(schema_editor, *models):
    if schema_editor is not None and getattr(schema_editor, "connection", None) is not None:
        alias = schema_editor.connection.alias
        return tuple(model.objects.using(alias) for model in models)
    return tuple(model.objects for model in models)


def _default_counts(Reaction) -> dict:
    """Return a fresh `{"total": 0, <type_name>: 0, ...}` dict for the given Reaction."""
    counts = {"total": 0}
    reaction_types = getattr(Reaction, "ReactionTypes", None)
    if reaction_types is not None:
        for rt in reaction_types:
            counts[rt.name] = 0
    return counts


def seed_reactable_metadata_from_reactions(
    apps,
    schema_editor,
    *,
    metadata_app_label: str = "baseapp_reactions",
    metadata_model_name: str = "ReactableMetadata",
):
    """
    Create or update one `ReactableMetadata` row per `DocumentId` referenced as a
    `Reaction.target_document`, populating per-type counts from a fresh GROUP BY.
    """
    Reaction = get_apps_model(apps, "baseapp_reactions", "Reaction")
    ReactableMetadata = get_apps_model(apps, metadata_app_label, metadata_model_name)
    reaction_qs, metadata_qs = _alias_pinned_managers(schema_editor, Reaction, ReactableMetadata)

    target_doc_ids = list(
        reaction_qs.exclude(target_document__isnull=True)
        .values_list("target_document_id", flat=True)
        .distinct()
    )

    # Build a (doc_id -> {reaction_type: int -> count}) map with a single GROUP BY.
    from django.db.models import Count

    grouped = (
        reaction_qs.exclude(target_document__isnull=True)
        .values("target_document_id", "reaction_type")
        .annotate(n=Count("id"))
    )
    per_doc: dict[int, dict[int, int]] = {}
    for row in grouped:
        per_doc.setdefault(row["target_document_id"], {})[row["reaction_type"]] = row["n"]

    reaction_types = getattr(Reaction, "ReactionTypes", None)
    type_name_by_value = (
        {int(rt.value): rt.name for rt in reaction_types} if reaction_types is not None else {}
    )

    for doc_id in target_doc_ids:
        counts = _default_counts(Reaction)
        for reaction_type_value, n in per_doc.get(doc_id, {}).items():
            name = type_name_by_value.get(int(reaction_type_value))
            if name is not None:
                counts[name] = n
            counts["total"] += n
        metadata_qs.update_or_create(
            target_id=doc_id,
            defaults={"reactions_count": counts},
        )


def reverse_seed_reactable_metadata(
    apps,
    schema_editor,
    *,
    metadata_app_label: str = "baseapp_reactions",
    metadata_model_name: str = "ReactableMetadata",
):
    """
    Drop `ReactableMetadata` rows that were seeded from existing `Reaction` data.
    Only rows whose `target_id` is referenced as a live `Reaction.target_document`
    are removed; unrelated metadata records are left untouched.
    """
    Reaction = get_apps_model(apps, "baseapp_reactions", "Reaction")
    ReactableMetadata = get_apps_model(apps, metadata_app_label, metadata_model_name)
    reaction_qs, metadata_qs = _alias_pinned_managers(schema_editor, Reaction, ReactableMetadata)

    doc_ids = list(
        reaction_qs.exclude(target_document__isnull=True)
        .values_list("target_document_id", flat=True)
        .distinct()
    )

    if doc_ids:
        metadata_qs.filter(target_id__in=doc_ids).delete()
