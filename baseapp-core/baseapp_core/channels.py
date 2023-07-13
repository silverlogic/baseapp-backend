from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware


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
