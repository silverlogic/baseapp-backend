"""graphql-transport-ws spike: connectionParams auth, Current-Profile, channel-layer broadcasts."""

import asyncio
from collections.abc import AsyncGenerator

import pytest
import strawberry
from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import RefreshToken
from strawberry.channels.testing import GraphQLWebsocketCommunicator
from strawberry.types import Info

from baseapp_core.strawberry.subscriptions import GraphQLWSConsumer, broadcast, listen
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio]


@strawberry.type
class Query:
    @strawberry.field
    def whoami(self, info: Info) -> str | None:
        user = info.context.user
        return user.email if user.is_authenticated else None


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def on_ping(self, info: Info) -> AsyncGenerator[str, None]:
        user = info.context.user
        if not user.is_authenticated:
            return
        profile = getattr(user, "current_profile", None)
        async for payload in listen(info, [f"user-{user.pk}"]):
            yield f"{payload['message']}:{profile.name if profile else '-'}"


schema = strawberry.Schema(query=Query, subscription=Subscription)
application = GraphQLWSConsumer.as_asgi(schema=schema)


async def _whoami(connection_params: dict) -> str | None:
    async with GraphQLWebsocketCommunicator(
        application, "/graphql", connection_params=connection_params
    ) as ws:
        async for result in ws.subscribe("{ whoami }"):
            return result.data["whoami"]


@database_sync_to_async
def _user_with_profile() -> tuple:
    user = UserFactory()
    profile = ProfileFactory(owner=user, name="Team Profile")
    refresh = RefreshToken.for_user(user)
    return user, profile.relay_id, str(refresh.access_token), str(refresh)


async def test_connection_params_authenticate_like_graphene_consumer() -> None:
    user, _, access, refresh = await _user_with_profile()

    assert await _whoami({}) is None
    assert await _whoami({"Authorization": "not-a-jwt"}) is None
    assert await _whoami({"Authorization": access, "Refresh": refresh}) == user.email


async def test_broadcast_reaches_subscriber_with_current_profile() -> None:
    user, profile_id, access, refresh = await _user_with_profile()
    params = {"Authorization": access, "Refresh": refresh, "Current-Profile": profile_id}

    async with GraphQLWebsocketCommunicator(
        application, "/graphql", connection_params=params
    ) as ws:
        first = asyncio.ensure_future(anext(aiter(ws.subscribe("subscription { onPing }"))))
        for _ in range(100):
            await sync_to_async(broadcast)(f"user-{user.pk}", {"message": "hello"})
            await asyncio.sleep(0.02)
            if first.done():
                break
        result = await first

    assert result.errors is None
    assert result.data == {"onPing": "hello:Team Profile"}
