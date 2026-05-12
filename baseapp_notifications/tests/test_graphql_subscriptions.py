import textwrap

import pytest
import swapper
from channels.db import database_sync_to_async

from baseapp_core.tests.factories import UserFactory

from .factories import NotificationFactory

pytestmark = pytest.mark.django_db(transaction=True)

Notification = swapper.load_model("notifications", "Notification")

SUBSCRIPTION_QUERY = textwrap.dedent("""
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
    """)


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

    # Since relay_id passes through the hashids strategies, it needs to be retrieved asynchronously.
    notification_relay_id = await database_sync_to_async(lambda: notification.relay_id)()

    # Check that subscription message were sent.
    resp = await client.receive(assert_id=sub_id, assert_type="next")
    assert (
        resp["data"]["onNotificationChange"]["createdNotification"]["node"]["id"]
        == notification_relay_id
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

    # Since relay_id passes through the hashids strategies, it needs to be retrieved asynchronously.
    notification_relay_id = await database_sync_to_async(lambda: notification.relay_id)()

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
        resp["data"]["onNotificationChange"]["updatedNotification"]["id"] == notification_relay_id
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

    # Since relay_id passes through the hashids strategies, it needs to be retrieved asynchronously.
    relay_id = await database_sync_to_async(lambda: notification.relay_id)()

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


@pytest.mark.asyncio
async def test_user_receives_bulk_created_notification_subscription_events(
    django_user_client, graphql_ws_user_client
):
    actor = await database_sync_to_async(UserFactory)()

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

    # Build two unsaved notification instances and bulk-create them.
    n1 = NotificationFactory.build(recipient=django_user_client.user, actor=actor)
    n2 = NotificationFactory.build(recipient=django_user_client.user, actor=actor)
    created = await database_sync_to_async(Notification.objects.bulk_create)([n1, n2])

    # Collect the relay IDs assigned after bulk_create.
    relay_ids = await database_sync_to_async(lambda: {n.relay_id for n in created})()

    # Expect one createdNotification event per bulk-created notification.
    received_ids = set()
    for _ in range(2):
        resp = await client.receive(assert_id=sub_id, assert_type="next")
        received_ids.add(
            resp["data"]["onNotificationChange"]["createdNotification"]["node"]["id"]
        )

    assert received_ids == relay_ids

    # Disconnect and wait the application to finish gracefully.
    await client.finalize()


@pytest.mark.asyncio
async def test_another_user_does_not_receive_bulk_created_notification_subscription_events(
    graphql_ws_user_client,
):
    actor = await database_sync_to_async(UserFactory)()
    other_recipient = await database_sync_to_async(UserFactory)()

    # Establish & initialize WebSocket GraphQL connection (authenticated as a different user).
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

    # Bulk-create notifications for a different user — the connected user must not receive events.
    n1 = NotificationFactory.build(recipient=other_recipient, actor=actor)
    n2 = NotificationFactory.build(recipient=other_recipient, actor=actor)
    await database_sync_to_async(Notification.objects.bulk_create)([n1, n2])

    await client.assert_no_messages()

    # Disconnect and wait the application to finish gracefully.
    await client.finalize()
