import warnings
from typing import Any


def __getattr__(name: str) -> Any:
    # `INVITATION_EXPIRATION_DAYS` used to be read once, at import. It is now computed on
    # each access so it follows `BASEAPP_PROFILES_INVITATION_EXPIRATION_DAYS`.
    if name == "INVITATION_EXPIRATION_DAYS":
        from .conf import invitation_expiration_days

        warnings.warn(
            "baseapp_profiles.constants.INVITATION_EXPIRATION_DAYS is deprecated; "
            "call baseapp_profiles.conf.invitation_expiration_days() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return invitation_expiration_days()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
