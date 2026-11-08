"""`onCommentChange` on the Strawberry schema, fed by the Graphene publishers through the bridge."""

import asyncio
from typing import Any

import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from rest_framework_simplejwt.tokens import RefreshToken
from strawberry.channels.testing import GraphQLWebsocketCommunicator

from baseapp_core.strawberry.subscriptions import GraphQLWSConsumer, subscription_group
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import CommentFactory

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio]

SUBSCRIPTION_QUERY = """
    subscription OnCommentChange($targetObjectId: ID) {
        onCommentChange(targetObjectId: $targetObjectId) {
            createdComment {
                node {
                    id
                    body
                }
            }
            updatedComment {
                id
                body
            }
            deletedCommentId
        }
    }
"""


def _application() -> Any:
    from testproject.strawberry_schema import schema

    return GraphQLWSConsumer.as_asgi(schema=schema)


async def _wait_for_subscriber(group: str) -> None:
    layer = get_channel_layer()
    for _ in range(250):
        if layer.groups.get(subscription_group("OnCommentChange", group)):
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"Nobody subscribed to {group}")


async def _next_update(results: Any, body: str) -> Any:
    """Skip the update events the factory's own saves publish."""
    async for result in results:
        updated = (result.data or {}).get("onCommentChange", {}).get("updatedComment")
        if result.errors or (updated and updated["body"] == body):
            return result


@database_sync_to_async
def _relay_id(obj) -> str:
    return obj.relay_id


@database_sync_to_async
def _update_body(comment, body: str) -> None:
    comment.body = body
    comment.save()


async def test_target_subscriber_receives_created_updated_and_deleted_comments() -> None:
    target = await database_sync_to_async(CommentFactory)()
    target_id = await _relay_id(target)

    async with GraphQLWebsocketCommunicator(_application(), "/graphql/strawberry") as ws:
        results = aiter(ws.subscribe(SUBSCRIPTION_QUERY, {"targetObjectId": target_id}))
        created = asyncio.ensure_future(anext(results))
        await _wait_for_subscriber(target_id)

        comment = await database_sync_to_async(CommentFactory)(target=target, body="first")
        comment_id = await _relay_id(comment)
        result = await created
        assert result.errors is None
        assert result.data["onCommentChange"] == {
            "createdComment": {"node": {"id": comment_id, "body": "first"}},
            "updatedComment": None,
            "deletedCommentId": None,
        }

        updated = asyncio.ensure_future(_next_update(results, "edited"))
        await _update_body(comment, "edited")
        result = await updated
        assert result.errors is None
        assert result.data["onCommentChange"]["updatedComment"] == {
            "id": comment_id,
            "body": "edited",
        }

        deleted = asyncio.ensure_future(anext(results))
        await database_sync_to_async(comment.delete)()
        result = await deleted
        assert result.errors is None
        assert result.data["onCommentChange"]["deletedCommentId"] == comment_id


async def test_user_with_view_all_permission_subscribes_to_every_comment() -> None:
    user = await database_sync_to_async(UserFactory)(is_superuser=True)
    profile = await database_sync_to_async(ProfileFactory)(owner=user)
    params = await database_sync_to_async(
        lambda: {
            "Authorization": str(RefreshToken.for_user(user).access_token),
            # CurrentProfileExtension would otherwise read `user.profile` on the event loop.
            "Current-Profile": profile.relay_id,
        }
    )()

    async with GraphQLWebsocketCommunicator(
        _application(), "/graphql/strawberry", connection_params=params
    ) as ws:
        created = asyncio.ensure_future(anext(aiter(ws.subscribe(SUBSCRIPTION_QUERY))))
        await _wait_for_subscriber("all")

        comment = await database_sync_to_async(CommentFactory)(body="anywhere")
        result = await created

    assert result.errors is None
    assert result.data["onCommentChange"]["createdComment"]["node"] == {
        "id": await _relay_id(comment),
        "body": "anywhere",
    }
