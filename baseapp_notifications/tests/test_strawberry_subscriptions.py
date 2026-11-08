"""`onNotificationChange` over graphql-transport-ws on the Strawberry schema."""

import asyncio
from typing import Any

import pytest
import swapper
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from rest_framework_simplejwt.tokens import RefreshToken
from strawberry.channels.testing import GraphQLWebsocketCommunicator

from baseapp_core.strawberry.subscriptions import GraphQLWSConsumer, subscription_group
from baseapp_core.tests.factories import UserFactory

from .factories import NotificationFactory

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio]

Notification = swapper.load_model("notifications", "Notification")

SUBSCRIPTION = """
    subscription {
      onNotificationChange {
        createdNotification {
          node {
            id
            unread
            level
            verb
            data
            actor { id __typename }
            recipient { id }
          }
        }
        updatedNotification { id unread }
        deletedNotificationId
      }
    }
"""


def _application() -> Any:
    from testproject.strawberry_schema import schema

    return GraphQLWSConsumer.as_asgi(schema=schema)


@database_sync_to_async
def _user_with_token() -> tuple[Any, dict[str, str]]:
    user = UserFactory()
    refresh = RefreshToken.for_user(user)
    # Current-Profile, as the frontend sends it: without it CurrentProfileExtension reads
    # `user.profile` synchronously inside the event loop.
    return user, {
        "Authorization": str(refresh.access_token),
        "Refresh": str(refresh),
        "Current-Profile": user.profile.relay_id,
    }


@database_sync_to_async
def _relay_id(instance: Any) -> str:
    return instance.relay_id


async def _wait_until_subscribed(user: Any) -> None:
    group = subscription_group("OnNotificationChange", str(user.pk))
    layer = get_channel_layer()
    for _ in range(200):
        if layer.groups.get(group):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("subscription never joined its group")


def _next_result(ws: GraphQLWebsocketCommunicator) -> "asyncio.Future[Any]":
    return asyncio.ensure_future(anext(aiter(ws.subscribe(SUBSCRIPTION))))


async def test_created_notification_reaches_the_recipient() -> None:
    user, params = await _user_with_token()
    async with GraphQLWebsocketCommunicator(
        _application(), "/graphql", connection_params=params
    ) as ws:
        result = _next_result(ws)
        await _wait_until_subscribed(user)
        notification = await database_sync_to_async(NotificationFactory)(recipient=user)
        result = await asyncio.wait_for(result, 5)

    assert result.errors is None
    node = result.data["onNotificationChange"]["createdNotification"]["node"]
    assert node["id"] == await _relay_id(notification)
    assert node["unread"] is True
    assert node["level"] == "INFO"
    assert node["actor"] == {"id": await _relay_id(notification.actor), "__typename": "User"}
    assert node["recipient"] == {"id": await _relay_id(user)}
    assert result.data["onNotificationChange"]["updatedNotification"] is None


async def test_updated_notification_reaches_the_recipient() -> None:
    user, params = await _user_with_token()
    notification = await database_sync_to_async(NotificationFactory)(recipient=user)
    async with GraphQLWebsocketCommunicator(
        _application(), "/graphql", connection_params=params
    ) as ws:
        result = _next_result(ws)
        await _wait_until_subscribed(user)
        notification.unread = False
        await notification.asave()
        result = await asyncio.wait_for(result, 5)

    assert result.errors is None
    assert result.data["onNotificationChange"]["updatedNotification"] == {
        "id": await _relay_id(notification),
        "unread": False,
    }


async def test_deleted_notification_reaches_the_recipient() -> None:
    user, params = await _user_with_token()
    notification = await database_sync_to_async(NotificationFactory)(recipient=user)
    relay_id = await _relay_id(notification)
    async with GraphQLWebsocketCommunicator(
        _application(), "/graphql", connection_params=params
    ) as ws:
        result = _next_result(ws)
        await _wait_until_subscribed(user)
        await notification.adelete()
        result = await asyncio.wait_for(result, 5)

    assert result.errors is None
    assert result.data["onNotificationChange"]["deletedNotificationId"] == relay_id


async def test_bulk_created_notifications_reach_only_their_recipient() -> None:
    user, params = await _user_with_token()
    other = await database_sync_to_async(UserFactory)()
    actor = await database_sync_to_async(UserFactory)()
    async with GraphQLWebsocketCommunicator(
        _application(), "/graphql", connection_params=params
    ) as ws:
        result = _next_result(ws)
        await _wait_until_subscribed(user)
        others = await database_sync_to_async(NotificationFactory.build)(
            recipient=other, actor=actor
        )
        mine = await database_sync_to_async(NotificationFactory.build)(recipient=user, actor=actor)
        await database_sync_to_async(Notification.objects.bulk_create)([others])
        created = await database_sync_to_async(Notification.objects.bulk_create)([mine])
        result = await asyncio.wait_for(result, 5)

    assert result.errors is None
    node = result.data["onNotificationChange"]["createdNotification"]["node"]
    assert node["id"] == await _relay_id(created[0])


async def test_anonymous_subscription_receives_nothing() -> None:
    user = await database_sync_to_async(UserFactory)()
    async with GraphQLWebsocketCommunicator(_application(), "/graphql") as ws:
        result = _next_result(ws)
        await asyncio.sleep(0.1)
        await database_sync_to_async(NotificationFactory)(recipient=user)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(result), 0.5)
        result.cancel()
