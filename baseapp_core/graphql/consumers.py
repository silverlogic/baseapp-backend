import asyncio
import contextvars
import functools
import sys
from typing import Any

import channels_graphql_ws
import swapper
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from graphene_django.settings import graphene_settings
from rest_framework.authtoken.models import Token

from baseapp_core.authentication import authenticate_jwt_async
from baseapp_core.graphql import get_pk_from_relay_id

python_version = sys.version_info

Profile = swapper.load_model("baseapp_profiles", "Profile")


async def threadpool_for_sync_resolvers(next_middleware, root, info, *args, **kwds) -> Any:
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

    async def on_connect(self, payload) -> None:
        if "user" in self.scope:
            # do nothing if already authenticated
            return

        if "Authorization" not in payload:
            self.scope["user"] = AnonymousUser()
            return

        token = await database_sync_to_async(
            Token.objects.select_related("user").filter(key=payload["Authorization"]).first
        )()

        try:
            user = token.user
        except AttributeError:
            user = None

        if user and user.is_active:
            self.scope["user"] = token.user
            if "Current-Profile" in payload:
                pk = await database_sync_to_async(get_pk_from_relay_id)(payload["Current-Profile"])
                if pk:
                    profile = await database_sync_to_async(Profile.objects.filter(pk=pk).first)()
                    if profile and await database_sync_to_async(user.has_perm)(
                        f"{profile._meta.app_label}.use_profile", profile
                    ):
                        token.user.current_profile = profile
        else:
            self.scope["user"] = AnonymousUser()
            return


class GraphqlWsJWTAuthenticatedConsumer(channels_graphql_ws.GraphqlWsConsumer):
    middleware = [threadpool_for_sync_resolvers]

    schema = graphene_settings.SCHEMA

    async def on_connect(self, payload) -> None:
        if "user" in self.scope:
            # do nothing if already authenticated
            return

        if not payload.get("Authorization"):
            self.scope["user"] = AnonymousUser()
            return

        # Refresh an expired access token instead of rejecting the connection, which —
        # with client retries — drove an endless reconnect loop.
        user, _ = await authenticate_jwt_async(payload["Authorization"], payload.get("Refresh"))

        if user and user.is_active:
            if "Current-Profile" in payload:
                pk = await database_sync_to_async(get_pk_from_relay_id)(payload["Current-Profile"])
                if pk:
                    profile = await database_sync_to_async(Profile.objects.filter(pk=pk).first)()
                    if profile and await database_sync_to_async(user.has_perm)(
                        f"{profile._meta.app_label}.use_profile", profile
                    ):
                        user.current_profile = profile

            self.scope["user"] = user
            return
        else:
            self.scope["user"] = AnonymousUser()
            return
