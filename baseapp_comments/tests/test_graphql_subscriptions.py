"""`onCommentChange` subscriptions, fed by the comment signal publishers."""

import asyncio
from typing import Any

import pytest
from channels.db import database_sync_to_async
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings

from baseapp_core.models import DocumentId
from baseapp_core.strawberry.subscriptions import subscription_group
from baseapp_core.strawberry.testing import next_result, wait_for_group, ws_communicator
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import CommentFactory

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


async def _wait_for_subscriber(group: str) -> None:
    await wait_for_group(subscription_group("OnCommentChange", group), timeout=5)


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


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_target_subscriber_receives_created_updated_and_deleted_comments() -> None:
    target = await database_sync_to_async(CommentFactory)()
    target_id = await _relay_id(target)

    async with await ws_communicator() as ws:
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


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_authenticated_subscriber_receives_created_comment(graphql_ws_user_client) -> None:
    target = await database_sync_to_async(CommentFactory)()
    target_id = await _relay_id(target)

    async with await graphql_ws_user_client() as ws:
        created = next_result(ws, SUBSCRIPTION_QUERY, {"targetObjectId": target_id})
        await _wait_for_subscriber(target_id)

        comment = await database_sync_to_async(CommentFactory)(target=target)
        result = await created

    assert result.errors is None
    assert result.data["onCommentChange"]["createdComment"]["node"]["id"] == await _relay_id(
        comment
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_user_with_view_all_permission_subscribes_to_every_comment() -> None:
    user = await database_sync_to_async(UserFactory)(is_superuser=True)
    await database_sync_to_async(ProfileFactory)(owner=user)

    async with await ws_communicator(user) as ws:
        created = next_result(ws, SUBSCRIPTION_QUERY)
        await _wait_for_subscriber("all")

        comment = await database_sync_to_async(CommentFactory)(body="anywhere")
        result = await created

    assert result.errors is None
    assert result.data["onCommentChange"]["createdComment"]["node"] == {
        "id": await _relay_id(comment),
        "body": "anywhere",
    }


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@override_settings(BASEAPP_COMMENTS_CAN_ANONYMOUS_VIEW_COMMENTS=False)
async def test_anon_cant_receive_created_comment_subscription_event() -> None:
    target = await database_sync_to_async(CommentFactory)()
    target_id = await _relay_id(target)

    async with await ws_communicator() as ws:
        created = next_result(ws, SUBSCRIPTION_QUERY, {"targetObjectId": target_id})
        await asyncio.sleep(0.1)

        await database_sync_to_async(CommentFactory)(target=target)
        done, _ = await asyncio.wait({created}, timeout=0.5)
        created.cancel()

    assert not done


@pytest.mark.django_db
def test_comment_subscription_when_target_is_not_found() -> None:
    comment = CommentFactory()
    missing_target_doc = DocumentId.objects.create(
        content_type=ContentType.objects.get_for_model(comment),
        object_id=999999,
    )
    comment.target_document = missing_target_doc
    comment.save()
