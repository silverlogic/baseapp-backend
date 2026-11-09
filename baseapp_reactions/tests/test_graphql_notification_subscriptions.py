import asyncio
import textwrap

import pytest
from channels.db import database_sync_to_async
from django.test import override_settings

from baseapp_comments.tests.factories import CommentFactory
from baseapp_core.graphql.testing.fixtures import graphql_query
from baseapp_core.strawberry.subscriptions import subscription_group
from baseapp_core.strawberry.testing import next_result, wait_for_group
from baseapp_core.tests.factories import UserFactory
from baseapp_core.tests.fixtures import DjangoClient

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

REACTION_TOGGLE_GRAPHQL = """
    mutation ReactionToggleMutation($input: ReactionToggleInput!) {
        reactionToggle(input: $input) {
            reaction {
                node {
                    id
                    reactionType
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
@override_settings(BASEAPP_REACTIONS_ENABLE_NOTIFICATIONS=True)
async def test_reaction_created_subscription_has_correct_unread_count(
    django_user_client, graphql_ws_user_client
) -> None:
    # Setup: User A (django_user_client.user) owns a comment (the reaction target)
    target = await database_sync_to_async(CommentFactory)(user=django_user_client.user)
    target_relay_id = await database_sync_to_async(lambda: target.relay_id)()

    # Subscribe as User A (the target owner who will receive the notification)
    async with await graphql_ws_user_client() as ws:
        created = next_result(ws, NOTIFICATION_SUBSCRIPTION_QUERY)
        await wait_for_group(
            subscription_group("OnNotificationChange", str(django_user_client.user.pk)), timeout=5
        )

        # Action: User B likes User A's comment via mutation
        liker = await database_sync_to_async(UserFactory)()
        liker_client = DjangoClient()
        await database_sync_to_async(liker_client.force_login)(liker)

        response = await database_sync_to_async(graphql_query)(
            REACTION_TOGGLE_GRAPHQL,
            variables={
                "input": {
                    "targetObjectId": target_relay_id,
                    "reactionType": "LIKE",
                }
            },
            client=liker_client,
        )
        content = response.json()
        assert "errors" not in content

        # Verify: subscription message has correct verb and unread count
        result = await asyncio.wait_for(created, timeout=5)
        assert result.errors is None
        notification = result.data["onNotificationChange"]["createdNotification"]["node"]
        assert notification["verb"] == "REACTIONS.REACTION_CREATED"
        assert notification["recipient"]["notificationsUnreadCount"] == 1
