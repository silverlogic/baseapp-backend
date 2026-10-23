from typing import Any

from rest_framework_simplejwt.tokens import AccessToken, RefreshToken, Token
from rest_framework_simplejwt.utils import datetime_to_epoch

from baseapp_auth.rest_framework.jwt.serializers import BaseJwtRefreshSerializer

from .services import validate_session_token


def _cap_exp(token_class: type[Token], raw: str, cap: int) -> str:
    # The token was minted a moment ago by the parent serializer, so it is not re-verified.
    token = token_class(raw, verify=False)
    if token["exp"] > cap:
        token["exp"] = cap
    return str(token)


class ImpersonationRefreshSerializerMixin:
    """
    Refuses to refresh a token whose impersonation session has ended or expired, and keeps
    the new tokens inside the session. Mix it in before a SimpleJWT refresh serializer.
    """

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        session = validate_session_token(RefreshToken(attrs["refresh"]))
        data = super().validate(attrs)
        if session is not None:
            cap = datetime_to_epoch(session.expires_at)
            data["access"] = _cap_exp(AccessToken, data["access"], cap)
            if "refresh" in data:
                data["refresh"] = _cap_exp(RefreshToken, data["refresh"], cap)
        return data


class ImpersonationJwtRefreshSerializer(
    ImpersonationRefreshSerializerMixin, BaseJwtRefreshSerializer
):
    """`BaseJwtRefreshSerializer` with the impersonation checks."""
