from typing import Any

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from baseapp_core.channels import JWTAuthMiddleware

from .exceptions import ImpersonationSessionInvalid
from .services import check_impersonation


def _check_scope_token(scope: dict, raw_token: str) -> None:
    try:
        token = AccessToken(raw_token)
    except TokenError:
        # Not ours to reject: the JWT middleware answers for a bad token.
        return
    check_impersonation(scope, token)


class ImpersonationWebsocketMiddleware(BaseMiddleware):
    """
    Validates the impersonation session of a WebSocket connection authenticated with a JWT
    `Authorization` subprotocol, and sets `scope["impersonation"]`.

    Wrap it inside `baseapp_core.channels.JWTAuthMiddleware`, so it sees the access token
    after any refresh: `JWTAuthMiddleware(ImpersonationWebsocketMiddleware(app))`. A
    connection whose session has ended is refused like an inactive user.
    """

    async def __call__(self, scope, receive, send) -> Any:
        subprotocols = scope.get("subprotocols") or []
        raw_token = JWTAuthMiddleware._subprotocol_value(subprotocols, "Authorization")
        if raw_token:
            try:
                await database_sync_to_async(_check_scope_token)(scope, raw_token)
            except ImpersonationSessionInvalid:
                raise ValueError("Impersonation session ended")
        return await super().__call__(scope, receive, send)
