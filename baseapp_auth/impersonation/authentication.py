from typing import Any

from rest_framework_simplejwt.authentication import JWTAuthentication

from .services import check_impersonation


class ImpersonationJWTAuthenticationMixin:
    """
    Validates impersonation tokens in a SimpleJWT-based authentication class.

    Mix it in before the JWT class: after the token authenticates, the session is checked,
    attached to the request and to the user (`user.impersonation`), and a read-only session
    refuses unsafe methods. Ordinary tokens pass through untouched.
    """

    def authenticate(self, request) -> "tuple[Any, Any] | None":
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        session = check_impersonation(request, token)
        if session is not None:
            user.impersonation = session
        return user, token


class ImpersonationJWTAuthentication(ImpersonationJWTAuthenticationMixin, JWTAuthentication):
    """Drop-in replacement for `rest_framework_simplejwt.authentication.JWTAuthentication`."""
