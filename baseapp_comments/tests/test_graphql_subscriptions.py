import textwrap

import pytest
import swapper
from channels.db import database_sync_to_async
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings

from .factories import CommentFactory

Comment = swapper.load_model("baseapp_comments", "Comment")

pytestmark = pytest.mark.django_db(transaction=True)

SUBSCRIPTION_QUERY = textwrap.dedent(
    """
    subscription op_name($targetObjectId: ID) {
      onCommentChange(targetObjectId: $targetObjectId) {
        createdComment {
          node {
            id
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
)


@pytest.mark.asyncio
async def test_user_recieves_created_comment_subscription_event(graphql_ws_user_client):
    # Establish & initialize WebSocket GraphQL connection.
    client = await graphql_ws_user_client(consumer_attrs={"strict_ordering": True})

    target = await database_sync_to_async(CommentFactory)()
    target_content_type = await database_sync_to_async(ContentType.objects.get_for_model)(target)

    # Subscribe to GraphQL subscription.
    sub_id = await client.send(
        msg_type="subscribe",
        payload={
            "query": SUBSCRIPTION_QUERY,
            "operationName": "op_name",
            "variables": {"targetObjectId": target.relay_id},
        },
    )
    await client.assert_no_messages()

    comment = await database_sync_to_async(CommentFactory)(
        target_object_id=target.pk, target_content_type=target_content_type
    )

    # Check that subscription message were sent.
    resp = await client.receive(assert_id=sub_id, assert_type="next")
    assert resp["data"]["onCommentChange"]["createdComment"]["node"]["id"] == comment.relay_id

    # Disconnect and wait the application to finish gracefully.
    await client.finalize()


@pytest.mark.asyncio
async def test_user_recieves_updated_comment_subscription_event(graphql_ws_user_client):
    # Establish & initialize WebSocket GraphQL connection.
    client = await graphql_ws_user_client(consumer_attrs={"strict_ordering": True})

    target = await database_sync_to_async(CommentFactory)()
    target_content_type = await database_sync_to_async(ContentType.objects.get_for_model)(target)

    comment = await database_sync_to_async(CommentFactory)(
        target_object_id=target.pk, target_content_type=target_content_type
    )

    # Subscribe to GraphQL subscription.
    sub_id = await client.send(
        msg_type="subscribe",
        payload={
            "query": SUBSCRIPTION_QUERY,
            "operationName": "op_name",
            "variables": {"targetObjectId": target.relay_id},
        },
    )
    await client.assert_no_messages()

    new_body = "updated body"
    comment.body = new_body
    await database_sync_to_async(comment.save)()

    # Check that subscription message were sent.
    resp = await client.receive(assert_id=sub_id, assert_type="next")

    assert resp["data"]["onCommentChange"]["updatedComment"]["id"] == comment.relay_id
    assert resp["data"]["onCommentChange"]["updatedComment"]["body"] == new_body

    # Disconnect and wait the application to finish gracefully.
    await client.finalize()


@pytest.mark.asyncio
async def test_user_recieves_deleted_comment_subscription_event(graphql_ws_user_client):
    # Establish & initialize WebSocket GraphQL connection.
    client = await graphql_ws_user_client(consumer_attrs={"strict_ordering": True})

    target = await database_sync_to_async(CommentFactory)()
    target_content_type = await database_sync_to_async(ContentType.objects.get_for_model)(target)

    comment = await database_sync_to_async(CommentFactory)(
        target_object_id=target.pk, target_content_type=target_content_type
    )

    # Subscribe to GraphQL subscription.
    sub_id = await client.send(
        msg_type="subscribe",
        payload={
            "query": SUBSCRIPTION_QUERY,
            "operationName": "op_name",
            "variables": {"targetObjectId": target.relay_id},
        },
    )
    await client.assert_no_messages()

    await database_sync_to_async(comment.delete)()

    # Check that subscription message were sent.
    resp = await client.receive(assert_id=sub_id, assert_type="next")

    assert resp["data"]["onCommentChange"]["deletedCommentId"] == comment.relay_id

    # Disconnect and wait the application to finish gracefully.
    await client.finalize()


@pytest.mark.asyncio
async def test_anon_recieves_created_comment_subscription_event(graphql_websocket):
    # Establish & initialize WebSocket GraphQL connection.
    client = graphql_websocket(consumer_attrs={"strict_ordering": True})

    target = await database_sync_to_async(CommentFactory)()
    target_content_type = await database_sync_to_async(ContentType.objects.get_for_model)(target)

    # Subscribe to GraphQL subscription.
    sub_id = await client.send(
        msg_type="subscribe",
        payload={
            "query": SUBSCRIPTION_QUERY,
            "operationName": "op_name",
            "variables": {"targetObjectId": target.relay_id},
        },
    )
    await client.assert_no_messages()

    comment = await database_sync_to_async(CommentFactory)(
        target_object_id=target.pk, target_content_type=target_content_type
    )

    # Check that subscription message were sent.
    resp = await client.receive(assert_id=sub_id, assert_type="next")
    assert resp["data"]["onCommentChange"]["createdComment"]["node"]["id"] == comment.relay_id

    # Disconnect and wait the application to finish gracefully.
    await client.finalize()


@pytest.mark.asyncio
@override_settings(BASEAPP_COMMENTS_CAN_ANONYMOUS_VIEW_COMMENTS=False)
async def test_anon_cant_recieve_created_comment_subscription_event(graphql_websocket):
    # Establish & initialize WebSocket GraphQL connection.
    client = graphql_websocket(consumer_attrs={"strict_ordering": True})

    target = await database_sync_to_async(CommentFactory)()
    target_content_type = await database_sync_to_async(ContentType.objects.get_for_model)(target)

    # Subscribe to GraphQL subscription.
    await client.send(
        msg_type="subscribe",
        payload={
            "query": SUBSCRIPTION_QUERY,
            "operationName": "op_name",
            "variables": {"targetObjectId": target.relay_id},
        },
    )
    await client.assert_no_messages()

    await database_sync_to_async(CommentFactory)(
        target_object_id=target.pk, target_content_type=target_content_type
    )

    # Check that n o subscription message were sent.
    await client.assert_no_messages()

    # Disconnect and wait the application to finish gracefully.
    await client.finalize()


def test_comment_subscription_when_target_is_not_found():
    comment = CommentFactory()
    comment.target_content_type = ContentType.objects.get_for_model(comment)
    comment.target_object_id = 999999  # non existent object
    comment.save()
