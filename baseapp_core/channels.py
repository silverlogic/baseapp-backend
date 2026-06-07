from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware

from baseapp_core.authentication import authenticate_jwt_async


@database_sync_to_async
def get_token_from_db(token_str):
    if not token_str:
        return None

    from rest_framework.authtoken.models import Token

    try:
        return Token.objects.select_related("user").get(key=token_str)
    except Token.DoesNotExist:
        return None


class TokenAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
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
    async def __call__(self, scope, receive, send):
        subprotocols = scope["subprotocols"]
        if "Authorization" not in subprotocols:
            raise ValueError("Missing token")

        access_token = self._subprotocol_value(subprotocols, "Authorization")
        refresh_token = self._subprotocol_value(subprotocols, "Refresh")

        user, new_access_token = await authenticate_jwt_async(access_token, refresh_token)
        if new_access_token:
            # propagate the refreshed token back to the negotiated subprotocols
            auth_index = subprotocols.index("Authorization")
            if auth_index + 1 < len(subprotocols):
                subprotocols[auth_index + 1] = new_access_token

        if user and not user.is_active:
            raise ValueError("User inactive or deleted")
        if user:
            scope["user"] = user

        return await super().__call__(scope, receive, send)

    @staticmethod
    def _subprotocol_value(subprotocols: list[str], key: str) -> str | None:
        """Return the value following ``key`` in the WS subprotocols, or ``None``."""
        if key not in subprotocols:
            return None
        try:
            return subprotocols[subprotocols.index(key) + 1]
        except IndexError:
            return None
