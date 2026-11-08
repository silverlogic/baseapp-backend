"""Subscriptions over graphql-transport-ws (the protocol of the frontend's `graphql-ws` client).

Replaces `baseapp_core.graphql.consumers` (channels_graphql_ws). Publishing moves from
`Subscription.broadcast(group=..., payload=...)` to `broadcast(group, payload)`; payloads go through
the channel layer, so they carry ids, not model instances.
"""

from collections.abc import AsyncGenerator, Sequence
from typing import Any

import swapper
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.contrib.auth.models import AnonymousUser
from strawberry.channels import GraphQLWSConsumer as StrawberryGraphQLWSConsumer
from strawberry.types import Info
from strawberry.types.unset import UNSET

from baseapp_core.authentication import authenticate_jwt_async
from baseapp_core.graphql import get_pk_from_relay_id

SUBSCRIPTION_MESSAGE_TYPE = "baseapp.subscription"


class WebSocketContext:
    """Request-like context, so resolvers keep reading `info.context.user`."""

    def __init__(self, consumer: StrawberryGraphQLWSConsumer) -> None:
        self.consumer = consumer
        self.channels_scope = consumer.scope
        self.connection_params: dict[str, Any] = {}
        self.user = consumer.scope.get("user") or AnonymousUser()
        self.headers: dict[str, str] = {}


@database_sync_to_async
def _current_profile(user: Any, relay_id: str) -> Any:
    Profile = swapper.load_model("baseapp_profiles", "Profile")
    pk = get_pk_from_relay_id(relay_id)
    profile = Profile.objects.filter(pk=pk).first() if pk else None
    if profile and user.has_perm(f"{profile._meta.app_label}.use_profile", profile):
        return profile
    return None


class GraphQLWSConsumer(StrawberryGraphQLWSConsumer):
    """Authenticates from `connectionParams` like `GraphqlWsJWTAuthenticatedConsumer`:
    `Authorization` (access JWT), `Refresh` (refresh JWT) and `Current-Profile` (relay id)."""

    async def get_context(self, request: Any, response: Any) -> WebSocketContext:
        return WebSocketContext(request)

    async def on_ws_connect(self, context: WebSocketContext) -> Any:
        params = context.connection_params or {}
        user = None
        if params.get("Authorization"):
            user, _ = await authenticate_jwt_async(params["Authorization"], params.get("Refresh"))
        if user is None or not user.is_active:
            user = AnonymousUser()
        elif params.get("Current-Profile"):
            user.current_profile = await _current_profile(user, params["Current-Profile"])
        context.user = user
        self.scope["user"] = user
        return UNSET


def broadcast(group: str, payload: dict[str, Any]) -> None:
    """Publish to every subscription listening on `group` (sync, safe to call from signals)."""
    async_to_sync(get_channel_layer().group_send)(
        group, {"type": SUBSCRIPTION_MESSAGE_TYPE, "payload": payload}
    )


async def listen(info: Info, groups: Sequence[str]) -> AsyncGenerator[dict[str, Any], None]:
    """Yield the payload of every `broadcast` to `groups` for the lifetime of the subscription."""
    async with info.context.consumer.listen_to_channel(
        SUBSCRIPTION_MESSAGE_TYPE, groups=groups
    ) as messages:
        async for message in messages:
            yield message["payload"]
