import logging

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


class JWTAuthMiddleware(BaseMiddleware):
    def __init__(self, inner, *args, **kwargs):
        from rest_framework_simplejwt.authentication import JWTAuthentication

        super().__init__(inner, *args, **kwargs)
        self._auth = JWTAuthentication()

    @database_sync_to_async
    def get_jwt_user_instance(self, token):
        from rest_framework_simplejwt.exceptions import (
            AuthenticationFailed,
            InvalidToken,
            TokenError,
        )

        if self._auth is None:
            raise RuntimeError("JWTAuthMiddleware not initialized")

        try:
            validated_token = self._auth.get_validated_token(token)
            return self._auth.get_user(validated_token)
        except (InvalidToken, AuthenticationFailed, TokenError) as e:
            logging.error(e)
            return None

    @database_sync_to_async
    def refresh_access_token(self, refresh_token):
        from rest_framework_simplejwt.exceptions import TokenError
        from rest_framework_simplejwt.tokens import RefreshToken

        try:
            refresh = RefreshToken(refresh_token)
            return str(refresh.access_token)
        except TokenError as e:
            logging.error(e)
            return None

    async def __call__(self, scope, receive, send):
        if "Authorization" not in scope["subprotocols"]:
            raise ValueError("Missing token")

        # handle token and user retrieval
        token_index = scope["subprotocols"].index("Authorization")
        try:
            token = scope["subprotocols"][token_index + 1]
        except IndexError:
            token = ""
        user = await self.get_jwt_user_instance(token)

        # handle token refresh
        if not user and "Refresh" in scope["subprotocols"]:
            refresh_index = scope["subprotocols"].index("Refresh")
            try:
                refresh_token = scope["subprotocols"][refresh_index + 1]
                new_access_token = await self.refresh_access_token(refresh_token)
                if new_access_token:
                    user = await self.get_jwt_user_instance(new_access_token)
                    scope["subprotocols"][token_index + 1] = new_access_token
            except IndexError:
                refresh_token = ""

        if user and not user.is_active:
            raise ValueError("User inactive or deleted")
        if user:
            scope["user"] = user

        return await super().__call__(scope, receive, send)
