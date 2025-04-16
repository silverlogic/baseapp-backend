import asyncio
import contextvars
import functools
import logging
import sys

import channels_graphql_ws
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from graphene_django.settings import graphene_settings
from rest_framework.authtoken.models import Token

python_version = sys.version_info


async def threadpool_for_sync_resolvers(next_middleware, root, info, *args, **kwds):
    if asyncio.iscoroutinefunction(next_middleware):
        result = await next_middleware(root, info, *args, **kwds)
    else:
        if python_version >= (3, 9):
            result = await asyncio.to_thread(next_middleware, root, info, *args, **kwds)
        else:
            loop = asyncio.get_running_loop()
            ctx = contextvars.copy_context()
            func_call = functools.partial(ctx.run, next_middleware, *args, **kwds)
            result = await loop.run_in_executor(None, func_call)
    return result


class GraphqlWsAuthenticatedConsumer(channels_graphql_ws.GraphqlWsConsumer):
    middleware = [threadpool_for_sync_resolvers]

    schema = graphene_settings.SCHEMA

    async def on_connect(self, payload):
        if "user" in self.scope:
            # do nothing if already authenticated
            return

        if "Authorization" not in payload:
            self.scope["user"] = AnonymousUser()
            return

        token = await database_sync_to_async(
            Token.objects.select_related("user").filter(key=payload["Authorization"]).first
        )()

        if token and token.user.is_active:
            self.scope["user"] = token.user
            return
        else:
            self.scope["user"] = AnonymousUser()
            return


class GraphqlWsJWTAuthenticatedConsumer(channels_graphql_ws.GraphqlWsConsumer):
    middleware = [threadpool_for_sync_resolvers]

    schema = graphene_settings.SCHEMA

    def __init__(self, *args, **kwargs):
        from rest_framework_simplejwt.authentication import (
            JWTAuthentication as RestJWTAuthentication,
        )
        from rest_framework_simplejwt.exceptions import (
            AuthenticationFailed,
            InvalidToken,
            TokenError,
        )

        self._auth = RestJWTAuthentication()
        self._exceptions = (AuthenticationFailed, InvalidToken, TokenError)

        return super().__init__(*args, **kwargs)

    @database_sync_to_async
    def get_jwt_user_instance(self, token_key):
        if self._auth is None or self._exceptions is None:
            raise RuntimeError("_setup method has to be called before.")

        try:
            validated_token = self._auth.get_validated_token(token_key)
            return self._auth.get_user(validated_token)
        except self._exceptions as e:
            logging.error(e)
            return None

    async def on_connect(self, payload):
        if "user" in self.scope:
            # do nothing if already authenticated
            return

        if "Authorization" not in payload:
            self.scope["user"] = AnonymousUser()
            return

        user = await self.get_jwt_user_instance(payload["Authorization"])

        if user and user.is_active:
            self.scope["user"] = user
            return
        else:
            self.scope["user"] = AnonymousUser()
            return
