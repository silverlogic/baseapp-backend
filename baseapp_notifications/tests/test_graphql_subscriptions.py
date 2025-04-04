import textwrap

import pytest
from channels.db import database_sync_to_async

from .factories import NotificationFactory

pytestmark = pytest.mark.django_db(transaction=True)

SUBSCRIPTION_QUERY = textwrap.dedent(
    """
    subscription op_name {
      onNotificationChange {
        createdNotification {
          node {
            id
          }
        }

        updatedNotification {
          id
          unread
        }

        deletedNotificationId
      }
    }
    """
)


@pytest.mark.asyncio
async def test_user_recieves_new_notification_subscription_event(
    django_user_client, graphql_ws_user_client
):
    # Establish & initialize WebSocket GraphQL connection.
    client = await graphql_ws_user_client(consumer_attrs={"strict_ordering": True})

    # Subscribe to GraphQL subscription.
    sub_id = await client.send(
        msg_type="subscribe",
        payload={
            "query": SUBSCRIPTION_QUERY,
            "operationName": "op_name",
        },
    )
    await client.assert_no_messages()

    notification = await database_sync_to_async(NotificationFactory)(
        recipient=django_user_client.user
    )

    # Check that subscription message were sent.
    resp = await client.receive(assert_id=sub_id, assert_type="next")
    assert (
        resp["data"]["onNotificationChange"]["createdNotification"]["node"]["id"]
        == notification.relay_id
    )

    # Disconnect and wait the application to finish gracefully.
    await client.finalize()


@pytest.mark.asyncio
async def test_another_user_do_not_recieves_new_notification_subscription_event(
    graphql_ws_user_client,
):
    # Establish & initialize WebSocket GraphQL connection.
    client = await graphql_ws_user_client(consumer_attrs={"strict_ordering": True})

    # Subscribe to GraphQL subscription.
    await client.send(
        msg_type="subscribe",
        payload={
            "query": SUBSCRIPTION_QUERY,
            "operationName": "op_name",
        },
    )
    await client.assert_no_messages()

    await database_sync_to_async(NotificationFactory)()

    # Check that subscription message were sent.
    await client.assert_no_messages()

    # Disconnect and wait the application to finish gracefully.
    await client.finalize()


@pytest.mark.asyncio
async def test_user_recieves_updated_notification_subscription_event(
    django_user_client, graphql_ws_user_client
):
    notification = await database_sync_to_async(NotificationFactory)(
        recipient=django_user_client.user
    )

    # Establish & initialize WebSocket GraphQL connection.
    client = await graphql_ws_user_client(consumer_attrs={"strict_ordering": True})

    # Subscribe to GraphQL subscription.
    sub_id = await client.send(
        msg_type="subscribe",
        payload={
            "query": SUBSCRIPTION_QUERY,
            "operationName": "op_name",
        },
    )
    await client.assert_no_messages()

    notification.unread = False
    await notification.asave()

    # Check that subscription message were sent.
    resp = await client.receive(assert_id=sub_id, assert_type="next")
    assert (
        resp["data"]["onNotificationChange"]["updatedNotification"]["id"] == notification.relay_id
    )
    assert resp["data"]["onNotificationChange"]["updatedNotification"]["unread"] is False

    # Disconnect and wait the application to finish gracefully.
    await client.finalize()


@pytest.mark.asyncio
async def test_user_recieves_deleted_notification_subscription_event(
    django_user_client, graphql_ws_user_client
):
    notification = await database_sync_to_async(NotificationFactory)(
        recipient=django_user_client.user
    )
    relay_id = notification.relay_id

    # Establish & initialize WebSocket GraphQL connection.
    client = await graphql_ws_user_client(consumer_attrs={"strict_ordering": True})

    # Subscribe to GraphQL subscription.
    sub_id = await client.send(
        msg_type="subscribe",
        payload={
            "query": SUBSCRIPTION_QUERY,
            "operationName": "op_name",
        },
    )
    await client.assert_no_messages()

    await notification.adelete()

    # Check that subscription message were sent.
    resp = await client.receive(assert_id=sub_id, assert_type="next")
    assert resp["data"]["onNotificationChange"]["deletedNotificationId"] == relay_id

    # Disconnect and wait the application to finish gracefully.
    await client.finalize()
