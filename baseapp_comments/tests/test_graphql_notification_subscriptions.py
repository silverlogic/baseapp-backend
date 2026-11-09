import asyncio
import textwrap

import pytest
from channels.db import database_sync_to_async
from django.test import override_settings

from baseapp_core.graphql.testing.fixtures import graphql_query
from baseapp_core.strawberry.subscriptions import subscription_group
from baseapp_core.strawberry.testing import next_result, wait_for_group
from baseapp_core.tests.factories import UserFactory
from baseapp_core.tests.fixtures import DjangoClient

from .factories import CommentFactory

pytestmark = pytest.mark.django_db(transaction=True)

NOTIFICATION_SUBSCRIPTION_QUERY = textwrap.dedent("""
    subscription op_name {
      onNotificationChange {
        createdNotification {
          node {
            id
            verb
            recipient {
              id
              notificationsUnreadCount
            }
          }
        }
      }
    }
    """)

COMMENT_CREATE_GRAPHQL = """
    mutation CommentCreateMutation($input: CommentCreateInput!) {
        commentCreate(input: $input) {
            comment {
                node {
                    id
                    body
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""


@pytest.mark.asyncio
@override_settings(BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS=True)
async def test_comment_created_subscription_has_correct_unread_count(
    django_user_client, graphql_ws_user_client
) -> None:
    # Setup: django_user_client.user (User A) owns a comment target
    target = await database_sync_to_async(CommentFactory)(user=django_user_client.user)
    target_relay_id = await database_sync_to_async(lambda: target.relay_id)()

    # Subscribe as User A (the target owner who will receive the notification)
    async with await graphql_ws_user_client() as ws:
        created = next_result(ws, NOTIFICATION_SUBSCRIPTION_QUERY)
        await wait_for_group(
            subscription_group("OnNotificationChange", str(django_user_client.user.pk)), timeout=5
        )

        # Action: User B creates a comment on User A's target
        commenter = await database_sync_to_async(UserFactory)()
        commenter_client = DjangoClient()
        await database_sync_to_async(commenter_client.force_login)(commenter)

        response = await database_sync_to_async(graphql_query)(
            COMMENT_CREATE_GRAPHQL,
            variables={
                "input": {
                    "targetObjectId": target_relay_id,
                    "body": "Nice comment!",
                }
            },
            client=commenter_client,
        )
        content = response.json()
        assert "errors" not in content

        # Verify: subscription message has correct verb and unread count
        result = await asyncio.wait_for(created, timeout=5)
        assert result.errors is None
        notification = result.data["onNotificationChange"]["createdNotification"]["node"]
        assert notification["verb"] == "COMMENTS.COMMENT_CREATED"
        assert notification["recipient"]["notificationsUnreadCount"] == 1


@pytest.mark.asyncio
@override_settings(BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS=True)
async def test_comment_reply_subscription_has_correct_unread_count(
    django_user_client, graphql_ws_user_client
) -> None:
    # Setup: User C owns a target, User A (django_user_client.user) writes a parent comment on it
    target_owner = await database_sync_to_async(UserFactory)()
    target = await database_sync_to_async(CommentFactory)(user=target_owner)
    target_relay_id = await database_sync_to_async(lambda: target.relay_id)()

    user_a_client = DjangoClient()
    await database_sync_to_async(user_a_client.force_login)(django_user_client.user)

    response = await database_sync_to_async(graphql_query)(
        COMMENT_CREATE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": target_relay_id,
                "body": "Parent comment",
            }
        },
        client=user_a_client,
    )
    content = response.json()
    assert "errors" not in content
    parent_comment_id = content["data"]["commentCreate"]["comment"]["node"]["id"]

    # Subscribe as User A (the parent comment author)
    async with await graphql_ws_user_client() as ws:
        created = next_result(ws, NOTIFICATION_SUBSCRIPTION_QUERY)
        await wait_for_group(
            subscription_group("OnNotificationChange", str(django_user_client.user.pk)), timeout=5
        )

        # Action: User B replies to User A's comment
        replier = await database_sync_to_async(UserFactory)()
        replier_client = DjangoClient()
        await database_sync_to_async(replier_client.force_login)(replier)

        response = await database_sync_to_async(graphql_query)(
            COMMENT_CREATE_GRAPHQL,
            variables={
                "input": {
                    "targetObjectId": target_relay_id,
                    "body": "Reply to your comment!",
                    "inReplyToId": parent_comment_id,
                }
            },
            client=replier_client,
        )
        content = response.json()
        assert "errors" not in content

        # Verify: subscription message has correct verb and unread count
        result = await asyncio.wait_for(created, timeout=5)
        assert result.errors is None
        notification = result.data["onNotificationChange"]["createdNotification"]["node"]
        assert notification["verb"] == "COMMENTS.COMMENT_REPLY_CREATED"
        assert notification["recipient"]["notificationsUnreadCount"] == 1
