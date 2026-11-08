"""Strawberry port of `OnNewActivityLogMessage` (registered in neither schema yet)."""

import asyncio
from typing import Any
from unittest.mock import patch

import pghistory
import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.apps import apps as django_apps
from rest_framework_simplejwt.tokens import RefreshToken
from strawberry.channels.testing import GraphQLWebsocketCommunicator

from baseapp.activity_log.graphql.subscriptions import OnNewActivityLogMessage
from baseapp.activity_log.models import ActivityLog, VisibilityTypes
from baseapp.activity_log.strawberry.types import activity_log_interfaces
from baseapp_comments.tests.factories import CommentFactory
from baseapp_core.strawberry.subscriptions import GraphQLWSConsumer, subscription_group
from baseapp_core.tests.factories import UserFactory

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio]

SUBSCRIPTION = """
    subscription ($roomId: ID!) {
      onNewActivityLog(roomId: $roomId) {
        message { node { id verb visibility user { id } } }
      }
    }
"""


def _application() -> Any:
    from baseapp.activity_log.strawberry.subscriptions import ActivityLogSubscriptions
    from baseapp_auth.strawberry.queries import UsersQueries
    from baseapp_core.plugins import plugin_registry
    from baseapp_core.strawberry.schema import build_schema

    schema = build_schema(
        queries=[UsersQueries, *plugin_registry.get_all_strawberry_queries()],
        subscriptions=[ActivityLogSubscriptions],
        types=plugin_registry.get_all_strawberry_types(),
    )
    return GraphQLWSConsumer.as_asgi(schema=schema)


@database_sync_to_async
def _setup() -> tuple[Any, dict[str, str], ActivityLog, str]:
    user = UserFactory()
    with pghistory.context(user=user.pk, visibility=VisibilityTypes.PUBLIC, verb="add_comment"):
        CommentFactory()
    refresh = RefreshToken.for_user(user)
    params = {
        "Authorization": str(refresh.access_token),
        "Refresh": str(refresh),
        "Current-Profile": user.profile.relay_id,
    }
    return user, params, ActivityLog.objects.get(), user.profile.relay_id


async def _wait_until_subscribed(room_id: str) -> None:
    group = subscription_group("OnNewActivityLogMessage", room_id)
    layer = get_channel_layer()
    for _ in range(200):
        if layer.groups.get(group):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("subscription never joined its group")


async def test_new_message_reaches_room_subscribers() -> None:
    user, params, activity, room_id = await _setup()
    async with GraphQLWebsocketCommunicator(
        _application(), "/graphql", connection_params=params
    ) as ws:
        result = asyncio.ensure_future(
            anext(aiter(ws.subscribe(SUBSCRIPTION, variables={"roomId": room_id})))
        )
        await _wait_until_subscribed(room_id)
        await database_sync_to_async(OnNewActivityLogMessage.new_message)(
            message=activity, room_id=room_id
        )
        result = await asyncio.wait_for(result, 5)

    assert result.errors is None
    node = result.data["onNewActivityLog"]["message"]["node"]
    assert node["id"] == await database_sync_to_async(lambda: activity.relay_id)()
    assert node["verb"] == "add_comment"
    assert node["visibility"] == "PUBLIC"
    assert node["user"]["id"] == await database_sync_to_async(lambda: user.relay_id)()


async def test_anonymous_subscriber_joins_no_room() -> None:
    _, _, _, room_id = await _setup()
    async with GraphQLWebsocketCommunicator(_application(), "/graphql") as ws:
        result = asyncio.ensure_future(
            anext(aiter(ws.subscribe(SUBSCRIPTION, variables={"roomId": room_id})))
        )
        await asyncio.sleep(0.2)
        assert not get_channel_layer().groups.get(
            subscription_group("OnNewActivityLogMessage", room_id)
        )
        result.cancel()


async def test_profile_interface_is_dropped_without_baseapp_profiles() -> None:
    original = django_apps.is_installed
    with patch.object(
        django_apps,
        "is_installed",
        side_effect=lambda name: name != "baseapp_profiles" and original(name),
    ):
        assert activity_log_interfaces() == ()
    assert len(activity_log_interfaces()) == 1
