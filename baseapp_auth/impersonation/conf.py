"""
Settings for ``baseapp_auth.impersonation``.

Every setting has a default here, so the app behaves the same whether or not the project
loads the plugin's ``django_extra_settings``. Values are read at call time so tests and
projects can override them with ``override_settings``.
"""

from datetime import timedelta
from typing import Any, Callable

from django.conf import settings
from django.utils.module_loading import import_string

DEFAULTS: dict[str, Any] = {
    # Session length. Seconds or a timedelta.
    "BASEAPP_AUTH_IMPERSONATION_TTL": 60 * 60,
    # True: a session can only read. False: "act as" — writes go through and are recorded.
    "BASEAPP_AUTH_IMPERSONATION_READ_ONLY": True,
    # Dotted path to callable(impersonator, target, request) -> bool.
    "BASEAPP_AUTH_IMPERSONATION_CAN_IMPERSONATE": (
        "baseapp_auth.impersonation.permissions.default_can_impersonate"
    ),
    # Dotted path to callable(refresh, target, impersonator) that may add claims.
    "BASEAPP_AUTH_IMPERSONATION_TOKEN_HOOK": None,
    # Writes allowed in a read-only session: GraphQL mutation names, or path regexes
    # (entries starting with "/" or "^").
    "BASEAPP_AUTH_IMPERSONATION_READ_ONLY_ALLOWLIST": (),
    # Writes refused in every session, even when acting as the user: account security, which
    # an impersonator must never change. Same format as the allowlist; it wins over it.
    "BASEAPP_AUTH_IMPERSONATION_DENYLIST": (
        r"^/v1/users/change-password",
        r"^/v1/users/delete-account",
        r"^/v1/change-email",
        r"^/v1/auth/mfa/",
    ),
    # Permissions refused to the impersonated user while a session is active.
    "BASEAPP_AUTH_IMPERSONATION_DENIED_PERMISSIONS": (),
    # How long a session lookup is cached, in seconds. Ending a session clears it at once.
    "BASEAPP_AUTH_IMPERSONATION_CACHE_TIMEOUT": 30,
}


def get_setting(name: str) -> Any:
    return getattr(settings, name, DEFAULTS[name])


def get_ttl() -> timedelta:
    ttl = get_setting("BASEAPP_AUTH_IMPERSONATION_TTL")
    if isinstance(ttl, timedelta):
        return ttl
    return timedelta(seconds=int(ttl))


def is_read_only() -> bool:
    return bool(get_setting("BASEAPP_AUTH_IMPERSONATION_READ_ONLY"))


def _load_callable(value: "str | Callable | None") -> "Callable | None":
    if not value:
        return None
    if isinstance(value, str):
        return import_string(value)
    return value


def get_can_impersonate() -> Callable:
    return _load_callable(get_setting("BASEAPP_AUTH_IMPERSONATION_CAN_IMPERSONATE"))


def get_token_hook() -> "Callable | None":
    return _load_callable(get_setting("BASEAPP_AUTH_IMPERSONATION_TOKEN_HOOK"))


def get_read_only_allowlist() -> tuple[str, ...]:
    return tuple(get_setting("BASEAPP_AUTH_IMPERSONATION_READ_ONLY_ALLOWLIST") or ())


def get_denylist() -> tuple[str, ...]:
    return tuple(get_setting("BASEAPP_AUTH_IMPERSONATION_DENYLIST") or ())


def get_denied_permissions() -> frozenset[str]:
    return frozenset(get_setting("BASEAPP_AUTH_IMPERSONATION_DENIED_PERMISSIONS") or ())


def get_cache_timeout() -> int:
    return int(get_setting("BASEAPP_AUTH_IMPERSONATION_CACHE_TIMEOUT"))
