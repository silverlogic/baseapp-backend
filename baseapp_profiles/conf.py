"""
Settings read by the membership and invitation services.

Each one is read at call time, so `override_settings` and the `settings` fixture work, and
each default keeps the behaviour projects had before the setting existed. The defaults are
also registered through the plugin's `django_extra_settings`.
"""

from typing import Any, Callable

from django.conf import settings
from django.utils.module_loading import import_string

DEFAULTS = {
    # Lets an invitee with no account accept anonymously by choosing a password.
    "BASEAPP_PROFILES_INVITATION_SIGNUP_ENABLED": False,
    # Cancel marks the row CANCELLED and a re-invite adds a new row, so declined, expired and
    # cancelled invitations stay on record. Off: cancel deletes and a re-invite reuses the row.
    "BASEAPP_PROFILES_INVITATION_KEEP_HISTORY": False,
    # Send invitation emails from a Celery task queued on commit (inline while Celery is eager).
    "BASEAPP_PROFILES_INVITATION_ASYNC_SEND": False,
    # Dotted path to `callable(invitation) -> bool`; True holds the email until released.
    "BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK": None,
    # Refuse to remove, demote or deactivate the last active ADMIN even when the profile has
    # an owner. Ownerless profiles are always protected.
    "BASEAPP_PROFILES_PROTECT_LAST_ADMIN": False,
    # Per-IP rate of the public invitation lookup and accept-with-signup REST endpoints.
    "BASEAPP_PROFILES_INVITATION_PUBLIC_RATE": "30/hour",
}


def _get(name: str) -> Any:
    return getattr(settings, name, DEFAULTS[name])


def invitation_signup_enabled() -> bool:
    return bool(_get("BASEAPP_PROFILES_INVITATION_SIGNUP_ENABLED"))


def keep_invitation_history() -> bool:
    return bool(_get("BASEAPP_PROFILES_INVITATION_KEEP_HISTORY"))


def invitation_async_send() -> bool:
    return bool(_get("BASEAPP_PROFILES_INVITATION_ASYNC_SEND"))


def protect_last_admin() -> bool:
    return bool(_get("BASEAPP_PROFILES_PROTECT_LAST_ADMIN"))


def invitation_public_rate() -> str | None:
    return _get("BASEAPP_PROFILES_INVITATION_PUBLIC_RATE")


def invitation_expiration_days() -> int:
    # Predates the BASEAPP_PROFILES_ prefix; kept under its original name.
    return int(getattr(settings, "INVITATION_EXPIRATION_DAYS", 7))


def invitation_pre_send_hook() -> Callable | None:
    hook = _get("BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK")
    if isinstance(hook, str):
        return import_string(hook)
    return hook
