from typing import TYPE_CHECKING, Any

from django.contrib.auth.backends import BaseBackend, ModelBackend
from django.core.exceptions import PermissionDenied

from . import conf

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser
    from django.http import HttpRequest


def default_can_impersonate(
    impersonator: "AbstractBaseUser",
    target: "AbstractBaseUser",
    request: "HttpRequest | None" = None,
) -> bool:
    """Superusers may impersonate anyone who is not a superuser."""
    return bool(impersonator.is_superuser and not target.is_superuser)


class ImpersonationPermissionsBackend(BaseBackend):
    """
    Refuses `BASEAPP_AUTH_IMPERSONATION_DENIED_PERMISSIONS` to a user while they are being
    impersonated, e.g. to keep their private messages out of the session.

    It refuses by raising `PermissionDenied`, which stops Django from asking later backends,
    so list it first in `AUTHENTICATION_BACKENDS`. Django answers every permission check of
    an active superuser with True before asking any backend.
    """

    def get_user(self, user_id: Any) -> Any:
        # Django stores the first backend on sessions opened without authenticate() (e.g.
        # force_login), and later loads the user through it.
        return ModelBackend().get_user(user_id)

    def has_perm(self, user_obj: Any, perm: str, obj: Any = None) -> bool:
        if perm in conf.get_denied_permissions():
            from .services import is_impersonated

            if is_impersonated(user_obj):
                raise PermissionDenied
        return False
