from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware


class TokenAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        from rest_framework.authtoken.models import Token

        if "Authorization" not in scope["subprotocols"]:
            raise ValueError("Missing token")

        index_auth = scope["subprotocols"].index("Authorization")
        token = scope["subprotocols"][index_auth + 1]

        try:
            token = await database_sync_to_async(Token.objects.select_related("user").get)(
                key=token
            )
            if token.user.is_active:
                scope["user"] = token.user
        except Token.DoesNotExist:
            pass

        return await super().__call__(scope, receive, send)
