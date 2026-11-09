"""Subscriptions over graphql-transport-ws (the protocol of the frontend's `graphql-ws` client).

Publishers `broadcast(subscription_group(<name>, group), payload)`; subscriptions `listen` on the
same groups. Payloads cross the channel layer: model instances travel as references and are
re-fetched.
"""

import hashlib
from collections.abc import AsyncGenerator, Sequence
from typing import Any

import swapper
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from strawberry.channels import GraphQLWSConsumer as StrawberryGraphQLWSConsumer
from strawberry.types import Info
from strawberry.types.unset import UNSET

from baseapp_core.authentication import authenticate_jwt_async
from baseapp_core.graphql import get_pk_from_relay_id

SUBSCRIPTION_MESSAGE_TYPE = "baseapp.subscription"
_MODEL_MARKER = "__baseapp_model__"


def subscription_group(subscription_name: str, group: Any = None) -> str:
    """Channel-layer group for `subscription_name` + `group` (hashed: any string is valid)."""
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
        self.headers: dict[str, str] = {
            k.decode("latin1"): v.decode("latin1") for k, v in consumer.scope.get("headers", [])
        }

    def build_absolute_uri(self, location: str = "/") -> str:
        """Like `HttpRequest.build_absolute_uri`, from the handshake's host and scheme."""
        from urllib.parse import urlsplit

        from django.conf import settings

        if urlsplit(location).scheme:
            return location
        host = self.headers.get("x-forwarded-host") or self.headers.get("host")
        if not host:
            return f"{getattr(settings, 'URL', '').rstrip('/')}{location}"
        secure = self.channels_scope.get("scheme") in ("wss", "https")
        scheme = self.headers.get("x-forwarded-proto") or ("https" if secure else "http")
        return f"{scheme}://{host}{location}"


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

    def __init__(self, *args: Any, allowed_origins: Sequence[str] | None = None, **kwargs: Any):
        if allowed_origins is None:
            # Auth is token-only (no cookies), so any origin is safe by default.
            allowed_origins = getattr(settings, "STRAWBERRY_WS_ALLOWED_ORIGINS", ("*",))
        super().__init__(*args, allowed_origins=allowed_origins, **kwargs)

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
