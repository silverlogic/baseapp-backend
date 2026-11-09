"""Helpers for testing subscriptions over graphql-transport-ws."""

import asyncio
from typing import Any

from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from strawberry.channels.testing import GraphQLWebsocketCommunicator


def _connection_params(user: Any, current_profile: bool) -> dict[str, str]:
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)
    params = {"Authorization": str(refresh.access_token), "Refresh": str(refresh)}
    profile = getattr(user, "profile", None) if current_profile else None
    if profile is not None:
        params["Current-Profile"] = profile.relay_id
    return params


async def ws_communicator(
    user: Any = None,
    *,
    current_profile: bool = True,
    path: str = "/graphql",
    **connection_params: Any,
) -> GraphQLWebsocketCommunicator:
    """A communicator on the project schema, authenticated as `user` like the frontend does
    (JWT `Authorization` + `Refresh`, and `Current-Profile` when the user has a profile)."""
    from .schema import get_schema
    from .subscriptions import GraphQLWSConsumer

    params = {}
    if user is not None:
        params = await database_sync_to_async(_connection_params)(user, current_profile)
    params.update(connection_params)
    application = GraphQLWSConsumer.as_asgi(schema=get_schema())
    # Browsers always send Host; resolvers build absolute URLs from it.
    headers = [(b"host", b"testserver")]
    return GraphQLWebsocketCommunicator(
        application, path, headers=headers, connection_params=params
    )


async def wait_for_group(group: str, timeout: float = 2.0) -> None:
    """Wait until a subscription joined `group` on the (in-memory) channel layer."""
    layer = get_channel_layer()
    for _ in range(int(timeout / 0.01)):
        if layer.groups.get(group):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"no subscription joined {group}")


def next_result(
    ws: GraphQLWebsocketCommunicator, query: str, variables: dict | None = None
) -> "asyncio.Future[Any]":
    """Subscribe and return a future for the first result."""
    return asyncio.ensure_future(anext(aiter(ws.subscribe(query, variables))))
