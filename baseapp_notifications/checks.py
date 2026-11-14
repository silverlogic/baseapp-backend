from typing import Any

from django.core.checks import Error, register


@register()
def check_email_sender(app_configs: Any = None, **kwargs: Any) -> list[Error]:
    """Fail at startup, not inside a send, when ``BASEAPP_NOTIFICATIONS_EMAIL_SENDER`` is wrong."""
    from .services import get_email_sender

    try:
        sender = get_email_sender()
    except ImportError as exc:
        return [
            Error(
                f"BASEAPP_NOTIFICATIONS_EMAIL_SENDER cannot be imported: {exc}",
                hint="Set it to the dotted path of callable(recipient, notification, **context).",
                id="baseapp_notifications.E001",
            )
        ]
    if not callable(sender):
        return [
            Error(
                "BASEAPP_NOTIFICATIONS_EMAIL_SENDER does not point at a callable.",
                hint="Set it to the dotted path of callable(recipient, notification, **context).",
                id="baseapp_notifications.E002",
            )
        ]
    return []
