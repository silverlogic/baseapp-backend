from typing import Any, Optional

from django.conf import settings
from django.core import signing
from django.db import models
from django.utils.crypto import constant_time_compare, salted_hmac

from .registry import ProtectedFileSpec, UserType


class ProtectedDownloadTicket:
    """
    A short-lived download link bound to the user who minted it.

    The payload names the file (``k`` key, ``o`` object id, ``n`` stored name, so replacing
    the file kills the link), the user (``u``, plus ``h``, a fragment derived from the
    user's session auth hash, so a password change kills it) and the profile the user was
    acting as (``p``). The ticket view re-runs the access check as that user on every use.
    """

    SALT = "baseapp_files.protected_download"
    AUTH_SALT = "baseapp_files.protected_download.auth"

    @classmethod
    def max_age(cls) -> int:
        """Lifetime in seconds (``BASEAPP_FILES_DOWNLOAD_TICKET_MAX_AGE``)."""
        return int(getattr(settings, "BASEAPP_FILES_DOWNLOAD_TICKET_MAX_AGE", 300))

    @classmethod
    def auth_fragment(cls, user: UserType) -> Optional[str]:
        """A fragment of the user's session auth hash; None for anonymous users."""
        if not getattr(user, "is_authenticated", False):
            return None
        return salted_hmac(cls.AUTH_SALT, user.get_session_auth_hash()).hexdigest()[:16]

    @classmethod
    def mint(cls, spec: ProtectedFileSpec, obj: models.Model, user: UserType) -> str:
        """Sign a ticket for ``user`` to download ``obj``'s file once its access was checked."""
        authenticated = getattr(user, "is_authenticated", False)
        profile = getattr(user, "current_profile", None) if authenticated else None
        return signing.dumps(
            {
                "k": spec.key,
                "o": spec.get_lookup_value(obj),
                "u": user.pk if authenticated else None,
                "h": cls.auth_fragment(user),
                "p": getattr(profile, "pk", None),
                "n": spec.get_field_file(obj).name or "",
            },
            salt=cls.SALT,
            compress=True,
        )

    @classmethod
    def load(cls, ticket: str) -> dict[str, Any]:
        """
        The ticket's payload.

        Raises:
            signing.SignatureExpired: older than ``max_age``.
            signing.BadSignature: tampered with or not a ticket.
        """
        return signing.loads(ticket, salt=cls.SALT, max_age=cls.max_age())

    @classmethod
    def auth_matches(cls, payload: dict[str, Any], user: UserType) -> bool:
        expected = payload.get("h")
        actual = cls.auth_fragment(user)
        if expected is None or actual is None:
            return expected is None and actual is None
        return constant_time_compare(expected, actual)
