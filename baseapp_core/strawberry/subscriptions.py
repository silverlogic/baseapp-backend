"""Subscriptions over graphql-transport-ws (the protocol of the frontend's `graphql-ws` client).

Replaces `baseapp_core.graphql.consumers` (channels_graphql_ws). While both schemas exist, every
Graphene `Subscription.broadcast(group=..., payload=...)` is bridged to the Strawberry group
`subscription_group(<SubscriptionClass name>, group)`; Strawberry subscriptions `listen` there.
Payloads cross the channel layer: model instances travel as references and are re-fetched.
"""

import hashlib
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
_MODEL_MARKER = "__baseapp_model__"


def subscription_group(subscription_name: str, group: Any = None) -> str:
    """Channel-layer group for `subscription_name` + Graphene group (hashed: any string is valid)."""
    digest = hashlib.sha256(f"{subscription_name}:{group}".encode()).hexdigest()
    return f"baseapp-strawberry-{digest}"


def serialize_payload(value: Any) -> Any:
    from django.db.models import Model

    if isinstance(value, Model):
        return {_MODEL_MARKER: value._meta.label, "pk": value.pk}
    if isinstance(value, dict):
        return {k: serialize_payload(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_payload(v) for v in value]
    return value


def _deserialize_payload(value: Any) -> Any:
    from django.apps import apps

    if isinstance(value, dict):
        if _MODEL_MARKER in value:
            model = apps.get_model(value[_MODEL_MARKER])
            return model._base_manager.filter(pk=value["pk"]).first()
        return {k: _deserialize_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deserialize_payload(v) for v in value]
    return value


deserialize_payload = database_sync_to_async(_deserialize_payload)


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
    from django.apps import apps

    if not apps.is_installed("baseapp_profiles"):
        return None
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

    async def authenticate_connection(self, params: dict[str, Any]) -> Any:
        """The user for these `connectionParams` (None when they don't authenticate)."""
        if not params.get("Authorization"):
            return None
        user, _ = await authenticate_jwt_async(params["Authorization"], params.get("Refresh"))
        return user

    async def on_ws_connect(self, context: WebSocketContext) -> Any:
        params = context.connection_params or {}
        user = await self.authenticate_connection(params)
        if user is None or not user.is_active:
            user = AnonymousUser()
        elif params.get("Current-Profile"):
            user.current_profile = await _current_profile(user, params["Current-Profile"])
        else:
            # Same default as CurrentProfileExtension, resolved here because ORM access is
            # not allowed on the event loop once the operation runs.
            user.current_profile = await database_sync_to_async(
                lambda: getattr(user, "profile", None)
            )()
        context.user = user
        self.scope["user"] = user
        return UNSET


def _message(payload: dict[str, Any]) -> dict[str, Any]:
    return {"type": SUBSCRIPTION_MESSAGE_TYPE, "payload": serialize_payload(payload)}


def broadcast(group: str, payload: dict[str, Any]) -> None:
    """Publish to every subscription listening on `group` (sync, safe to call from signals)."""
    async_to_sync(get_channel_layer().group_send)(group, _message(payload))


async def broadcast_async(group: str, payload: dict[str, Any]) -> None:
    await get_channel_layer().group_send(group, _message(payload))


async def listen(info: Info, groups: Sequence[str]) -> AsyncGenerator[dict[str, Any], None]:
    """Yield the payload of every `broadcast` to `groups` for the lifetime of the subscription.

    Model instances in the payload are re-fetched from the database.
    """
    async with info.context.consumer.listen_to_channel(
        SUBSCRIPTION_MESSAGE_TYPE, groups=groups
    ) as messages:
        async for message in messages:
            yield await deserialize_payload(message["payload"])


def install_graphene_bridge() -> None:
    """Make every Graphene subscription broadcast reach the Strawberry subscribers too."""
    try:
        import channels_graphql_ws
    except ImportError:
        return
    subscription = channels_graphql_ws.Subscription
    if getattr(subscription, "_strawberry_bridged", False):
        return
    original_sync = subscription.broadcast_sync.__func__
    original_async = subscription.broadcast_async.__func__

    def broadcast_sync(cls: Any, *, group: Any = None, payload: Any = None) -> Any:
        result = original_sync(cls, group=group, payload=payload)
        broadcast(subscription_group(cls.__name__, group), payload or {})
        return result

    async def broadcast_async_bridge(cls: Any, *, group: Any = None, payload: Any = None) -> Any:
        result = await original_async(cls, group=group, payload=payload)
        await broadcast_async(subscription_group(cls.__name__, group), payload or {})
        return result

    subscription.broadcast_sync = classmethod(broadcast_sync)
    subscription.broadcast_async = classmethod(broadcast_async_bridge)
    subscription._strawberry_bridged = True
