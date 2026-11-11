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

    @strawberry.field
    def current_profile(self, info: Info) -> str | None:
        profile = getattr(info.context.user, "current_profile", None)
        return profile.name if profile else None


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


async def _query(connection_params: dict, query: str, app=application) -> dict:
    async with GraphQLWebsocketCommunicator(
        app, "/graphql", connection_params=connection_params
    ) as ws:
        async for result in ws.subscribe(query):
            assert result.errors is None
            return result.data


async def _whoami(connection_params: dict) -> str | None:
    return (await _query(connection_params, "{ whoami }"))["whoami"]


async def _current_profile(connection_params: dict) -> str | None:
    return (await _query(connection_params, "{ currentProfile }"))["currentProfile"]


@database_sync_to_async
def _user_with_profile() -> tuple:
    user = UserFactory()
    profile = ProfileFactory(owner=user, name="Team Profile")
    refresh = RefreshToken.for_user(user)
    return user, profile.relay_id, str(refresh.access_token), str(refresh)


async def test_connection_params_authenticate_like_the_frontend_sends_them() -> None:
    user, _, access, refresh = await _user_with_profile()

    assert await _whoami({}) is None
    assert await _whoami({"Authorization": "not-a-jwt"}) is None
    assert await _whoami({"Authorization": access, "Refresh": refresh}) == user.email


async def test_bad_access_token_falls_back_to_refresh_token() -> None:
    user, _, _, refresh = await _user_with_profile()

    assert await _whoami({"Authorization": "expired", "Refresh": refresh}) == user.email
    assert await _whoami({"Authorization": "expired", "Refresh": "bad"}) is None


async def test_inactive_user_is_anonymous() -> None:
    user, _, access, refresh = await _user_with_profile()
    user.is_active = False
    await user.asave(update_fields=["is_active"])

    assert await _whoami({"Authorization": access, "Refresh": refresh}) is None


async def test_current_profile_is_attached_only_when_usable() -> None:
    _, own_id, access, refresh = await _user_with_profile()
    other_id = await database_sync_to_async(lambda: ProfileFactory(name="Other").relay_id)()
    params = {"Authorization": access, "Refresh": refresh}

    assert await _current_profile({**params, "Current-Profile": own_id}) == "Team Profile"
    assert await _current_profile({**params, "Current-Profile": other_id}) is None
    assert await _current_profile({**params, "Current-Profile": "unknown"}) is None


async def test_missing_current_profile_defaults_to_the_users_profile() -> None:
    user, _, access, refresh = await _user_with_profile()
    name = await database_sync_to_async(lambda: user.profile.name)()

    assert await _current_profile({"Authorization": access, "Refresh": refresh}) == name


async def test_user_set_by_middleware_is_kept() -> None:
    user, _, _, _ = await _user_with_profile()

    async def with_user(scope, receive, send):
        return await application({**scope, "user": user}, receive, send)

    data = await _query({"Authorization": "not-a-jwt"}, "{ whoami }", app=with_user)
    assert data["whoami"] == user.email


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


async def _handshake(origin: str, **consumer_kwargs) -> bool:
    from channels.testing import WebsocketCommunicator

    communicator = WebsocketCommunicator(
        GraphQLWSConsumer.as_asgi(schema=schema, **consumer_kwargs),
        "/graphql",
        headers=[(b"host", b"api.example.com"), (b"origin", origin.encode())],
        subprotocols=["graphql-transport-ws"],
    )
    connected, _ = await communicator.connect()
    await communicator.disconnect()
    return connected


async def test_cross_origin_websocket_is_accepted_by_default() -> None:
    assert await _handshake("https://app.example.com")


async def test_cross_origin_websocket_respects_allowed_origins_setting(settings) -> None:
    settings.STRAWBERRY_WS_ALLOWED_ORIGINS = ["https://app.example.com"]
    assert await _handshake("https://app.example.com")
    assert not await _handshake("https://evil.example.org")
