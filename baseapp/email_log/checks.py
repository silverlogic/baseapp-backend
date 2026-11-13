from typing import Any

from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security)
def check_attachment_storage(app_configs: Any = None, **kwargs: Any) -> list[Warning]:
    """Stored attachments are often personal documents; default_storage is often public."""
    store = getattr(settings, "BASEAPP_EMAIL_LOG_STORE_ATTACHMENTS", False)
    if store and not getattr(settings, "BASEAPP_EMAIL_LOG_ATTACHMENT_STORAGE", None):
        return [
            Warning(
                "BASEAPP_EMAIL_LOG_STORE_ATTACHMENTS is on with no "
                "BASEAPP_EMAIL_LOG_ATTACHMENT_STORAGE, so email attachments are saved to "
                "default_storage, which is often publicly readable media.",
                hint="Point BASEAPP_EMAIL_LOG_ATTACHMENT_STORAGE at a private storage.",
                id="baseapp_email_log.W001",
            )
        ]
    return []


@register()
def check_retention_by_category(app_configs: Any = None, **kwargs: Any) -> list[Warning]:
    """A category with an unusable retention is skipped by the purge; say so at startup."""
    from .tasks import valid_retention_days

    by_category = getattr(settings, "BASEAPP_EMAIL_LOG_RETENTION_DAYS_BY_CATEGORY", None) or {}
    if not isinstance(by_category, dict):
        invalid = {"BASEAPP_EMAIL_LOG_RETENTION_DAYS_BY_CATEGORY": by_category}
    else:
        invalid = {
            category: days
            for category, days in by_category.items()
            if days is not None and not valid_retention_days(days)
        }
    if not invalid:
        return []
    return [
        Warning(
            "BASEAPP_EMAIL_LOG_RETENTION_DAYS_BY_CATEGORY must map categories to a number of "
            f"days (or None for no retention of their own); the purge skips {invalid!r}.",
            id="baseapp_email_log.W002",
        )
    ]
