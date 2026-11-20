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
    # Dotted path to `callable(user, invitation) -> bool` deciding whether accept-with-signup
    # may reactivate an existing inactive account. None: only accounts that never signed in.
    # Staff and superusers are never reactivated, whatever this returns.
    "BASEAPP_PROFILES_INVITATION_SIGNUP_CAN_REACTIVATE": None,
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
    # Most invitations a single send may contain. None: no limit.
    "BASEAPP_PROFILES_INVITATION_MAX_PER_SEND": None,
    # Lifetime of an invitation in days: an int, a callable returning one or a dotted path
    # to such a callable, read on every send. None: the legacy INVITATION_EXPIRATION_DAYS
    # setting, then 7.
    "BASEAPP_PROFILES_INVITATION_EXPIRATION_DAYS": None,
    # Dotted path to (or a) `callable(invitation, inviter) -> None` that emails an invitation.
    "BASEAPP_PROFILES_INVITATION_EMAIL_SENDER": "baseapp_profiles.emails.send_invitation_email",
    # Dotted path to `callable(profile, invitee, invited_by) -> None` that raises
    # ProfileMembershipError to refuse an invitee. None: every invitee is accepted.
    "BASEAPP_PROFILES_INVITATION_VALIDATOR": None,
    # Dotted path to `callable(membership) -> bool`: may an ACTIVE member be sent an
    # invitation that claims their row (a placeholder member without a usable account)?
    # None: inviting a member is refused with `already_member`.
    "BASEAPP_PROFILES_INVITATION_CAN_INVITE_MEMBER": None,
    # Seconds that must pass after an invitation email before it may be resent. None: no limit.
    "BASEAPP_PROFILES_INVITATION_RESEND_MIN_INTERVAL": None,
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


def invitation_max_per_send() -> int | None:
    value = _get("BASEAPP_PROFILES_INVITATION_MAX_PER_SEND")
    return None if value is None else int(value)


def _get_callable(name: str) -> Callable | None:
    hook = _get(name)
    if isinstance(hook, str):
        return import_string(hook)
    return hook


def invitation_expiration_days() -> int:
    """
    How many days a newly sent invitation stays valid.

    Every send, resend and release reads it, so a value computed at call time (a callable,
    say one reading a staff-editable setting) applies to the next invitation sent.
    Invitations already sent keep the expiry date they were given.
    """
    value = _get("BASEAPP_PROFILES_INVITATION_EXPIRATION_DAYS")
    if value is None:
        # The setting that predates the BASEAPP_PROFILES_ prefix.
        return int(getattr(settings, "INVITATION_EXPIRATION_DAYS", 7))
    if isinstance(value, str):
        value = import_string(value)
    if callable(value):
        value = value()
    return int(value)


def invitation_email_sender() -> Callable:
    return _get_callable("BASEAPP_PROFILES_INVITATION_EMAIL_SENDER") or import_string(
        DEFAULTS["BASEAPP_PROFILES_INVITATION_EMAIL_SENDER"]
    )


def invitation_validator() -> Callable | None:
    return _get_callable("BASEAPP_PROFILES_INVITATION_VALIDATOR")


def invitation_can_invite_member() -> Callable | None:
    return _get_callable("BASEAPP_PROFILES_INVITATION_CAN_INVITE_MEMBER")


def invitation_resend_min_interval() -> int | None:
    value = _get("BASEAPP_PROFILES_INVITATION_RESEND_MIN_INTERVAL")
    return None if value is None else int(value)


def invitation_pre_send_hook() -> Callable | None:
    return _get_callable("BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK")


def invitation_signup_can_reactivate() -> Callable | None:
    return _get_callable("BASEAPP_PROFILES_INVITATION_SIGNUP_CAN_REACTIVATE")
