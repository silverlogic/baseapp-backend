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
