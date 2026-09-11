from typing import TYPE_CHECKING, Any

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware

from baseapp_core.authentication import authenticate_jwt_async

if TYPE_CHECKING:
    from rest_framework.authtoken.models import Token

# WS auth subprotocols arrive as adjacent key/value pairs; these are the recognized keys,
# used to tell a key apart from a value when a key is sent without one.
SUBPROTOCOL_KEYS = ("Authorization", "Refresh")


@database_sync_to_async
def get_token_from_db(token_str) -> "Token | None":
    if not token_str:
        return None

    from rest_framework.authtoken.models import Token

    try:
        return Token.objects.select_related("user").get(key=token_str)
    except Token.DoesNotExist:
        return None


class TokenAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send) -> Any:
        if "Authorization" not in scope["subprotocols"]:
            raise ValueError("Missing token")

        index_auth = scope["subprotocols"].index("Authorization")
        try:
            token_str = scope["subprotocols"][index_auth + 1]
        except IndexError:
            token_str = ""

        token = await get_token_from_db(token_str)
        if token:
            scope["user"] = token.user

        if token and not token.user.is_active:
            raise ValueError("User inactive or deleted")

        return await super().__call__(scope, receive, send)


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send) -> Any:
        subprotocols = scope["subprotocols"]
        if "Authorization" not in subprotocols:
            raise ValueError("Missing token")

        access_token = self._subprotocol_value(subprotocols, "Authorization")
        refresh_token = self._subprotocol_value(subprotocols, "Refresh")

        user, new_access_token = await authenticate_jwt_async(access_token, refresh_token)
        if new_access_token:
            value_index = subprotocols.index("Authorization") + 1
            if (
                value_index < len(subprotocols)
                and subprotocols[value_index] not in SUBPROTOCOL_KEYS
            ):
                subprotocols[value_index] = new_access_token

        if user and not user.is_active:
            raise ValueError("User inactive or deleted")
        if user:
            scope["user"] = user

        return await super().__call__(scope, receive, send)

    @staticmethod
    def _subprotocol_value(subprotocols: list[str], key: str) -> str | None:
        """Return the value paired with ``key`` in the WS subprotocols, or ``None``.

        Subprotocols arrive as adjacent key/value pairs. Returns ``None`` when ``key`` is
        absent, or when the item after it is another known key (i.e. ``key`` has no value).
        """
        if key not in subprotocols:
            return None
        value_index = subprotocols.index(key) + 1
        if value_index >= len(subprotocols):
            return None
        value = subprotocols[value_index]
        return None if value in SUBPROTOCOL_KEYS else value
