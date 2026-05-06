"""
Reusable migration helper to seed default ``ReportType`` rows.

Reports does not depend on any other baseapp app, so the default ``ReportType``
content-type wiring is intentionally optional: pass the consumer apps that are
actually installed and the helper looks up their content types via Django's
historical ``apps.get_model``. Apps that aren't installed are silently skipped.

How to use in a project migration
---------------------------------
1. Make sure your migration depends on the migration that creates ``ReportType``
   in your project / testproject.
2. Add a ``RunPython`` operation that calls ``seed_default_report_types(...)``,
   passing whichever ``content_type_targets`` are relevant to your project.
3. Use ``reverse_seed_default_report_types(...)`` (or
   :func:`migrations.RunPython.noop`) as the reverse code.

Example:

    def forwards(apps, schema_editor):
        seed_default_report_types(
            apps,
            schema_editor,
            content_type_targets={
                "comment": ("baseapp_comments", "Comment"),
                "page": ("baseapp_pages", "Page"),
                "profile": ("baseapp_profiles", "Profile"),
            },
        )
"""

import pgtrigger

from baseapp_core.swapper import get_apps_model

DEFAULT_REPORT_TYPES = [
    {"key": "spam", "label": "Spam", "targets": ["comment"]},
    {"key": "inappropriate", "label": "Inappropriate", "targets": ["comment"]},
    {"key": "fake", "label": "Fake", "targets": ["comment"]},
    {"key": "other", "label": "Other", "targets": ["comment", "page", "profile"]},
    {"key": "scam", "label": "Scam or fraud", "targets": ["page", "profile"]},
    {"key": "adult_content", "label": "Adult Content", "targets": ["page", "profile"]},
    {"key": "violence", "label": "Violence, hate or exploitation", "targets": ["page", "profile"]},
    {"key": "bulling", "label": "Bulling or unwanted contact", "targets": ["page", "profile"]},
]

DEFAULT_ADULT_CONTENT_SUBTYPES = [
    {"key": "pornography", "label": "Pornography", "targets": ["page", "profile"]},
    {"key": "childAbuse", "label": "Child abuse", "targets": ["page", "profile"]},
    {"key": "prostituition", "label": "Prostituition", "targets": ["page", "profile"]},
]


def _get_report_type_uris(ReportType):
    concrete_report_type = ReportType._meta.concrete_model
    report_type_uri = (
        f"{concrete_report_type._meta.app_label}.{concrete_report_type._meta.object_name}"
    )
    return [f"{report_type_uri}:insert_document_id", f"{report_type_uri}:delete_document_id"]


def _resolve_content_types(apps, ContentType, content_type_targets):
    resolved = {}
    for alias, (app_label, model_name) in content_type_targets.items():
        try:
            Model = get_apps_model(apps, app_label, model_name)
        except LookupError:
            continue
        resolved[alias] = ContentType.objects.get_for_model(Model)
    return resolved


def seed_default_report_types(
    apps,
    schema_editor,
    *,
    content_type_targets=None,
    base_types=None,
    adult_content_subtypes=None,
):
    """
    Create default ``ReportType`` rows and (optionally) wire them up to existing
    project content types.

    ``content_type_targets`` maps an alias used in the type definitions
    (e.g. ``"comment"``) to a ``(app_label, model_name)`` tuple. Aliases not
    present in the map (or whose app is not installed) are silently dropped from
    each type's ``content_types`` set.
    """
    ReportType = get_apps_model(apps, "baseapp_reports", "ReportType")
    ContentType = get_apps_model(apps, "contenttypes", "ContentType")

    base_types = base_types or DEFAULT_REPORT_TYPES
    adult_content_subtypes = adult_content_subtypes or DEFAULT_ADULT_CONTENT_SUBTYPES

    resolved_cts = _resolve_content_types(apps, ContentType, content_type_targets or {})

    report_type_uris = _get_report_type_uris(ReportType)

    adult_content_type = None

    with pgtrigger.ignore(*report_type_uris):
        for spec in base_types:
            rt, _ = ReportType.objects.update_or_create(
                key=spec["key"],
                defaults={"label": spec["label"]},
            )
            cts = [resolved_cts[a] for a in spec.get("targets", []) if a in resolved_cts]
            if cts:
                rt.content_types.set(cts)
            if spec["key"] == "adult_content":
                adult_content_type = rt

        for spec in adult_content_subtypes:
            rt, _ = ReportType.objects.update_or_create(
                key=spec["key"],
                defaults={
                    "label": spec["label"],
                    "parent_type": adult_content_type,
                },
            )
            cts = [resolved_cts[a] for a in spec.get("targets", []) if a in resolved_cts]
            if cts:
                rt.content_types.set(cts)


def reverse_seed_default_report_types(apps, schema_editor):
    """Drop all ``ReportType`` rows."""
    ReportType = get_apps_model(apps, "baseapp_reports", "ReportType")
    report_type_uris = _get_report_type_uris(ReportType)
    with pgtrigger.ignore(*report_type_uris):
        ReportType.objects.all().delete()
