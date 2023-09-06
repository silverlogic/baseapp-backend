import asyncio

import channels_graphql_ws
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from graphene_django.settings import graphene_settings
from rest_framework.authtoken.models import Token


async def threadpool_for_sync_resolvers(next_middleware, root, info, *args, **kwds):
    if asyncio.iscoroutinefunction(next_middleware):
        result = await next_middleware(root, info, *args, **kwds)
    else:
        result = await asyncio.to_thread(next_middleware, root, info, *args, **kwds)
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
