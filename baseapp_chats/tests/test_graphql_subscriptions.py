import textwrap

import pytest
import swapper
from channels.db import database_sync_to_async

from baseapp_core.tests.factories import UserFactory

from ..utils import send_message
from .factories import ChatRoomFactory, ChatRoomParticipantFactory

Message = swapper.load_model("baseapp_chats", "Message")
Verbs = Message.Verbs

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.asyncio
async def test_user_recieves_news_message_subscription_event(
    django_user_client, graphql_ws_user_client
):
    room = await database_sync_to_async(ChatRoomFactory)(created_by=django_user_client.user)
    await database_sync_to_async(ChatRoomParticipantFactory)(
        profile=django_user_client.user.profile, room=room
    )
    user = await database_sync_to_async(UserFactory)()
    await database_sync_to_async(ChatRoomParticipantFactory)(room=room, profile=user.profile)

    # Establish & initialize WebSocket GraphQL connection.
    client = await graphql_ws_user_client(consumer_attrs={"strict_ordering": True})

    # Subscribe to GraphQL subscription.
    sub_id = await client.send(
        msg_type="subscribe",
        payload={
            "query": textwrap.dedent(
                """
                subscription op_name($roomId: ID!, $profileId: ID!) {
                  chatRoomOnMessage(roomId: $roomId, profileId: $profileId) {
                    message {
                      node {
                        id
                        content
                      }
                    }
                  }
                }
                """
            ),
            "variables": {
                "roomId": room.relay_id,
                "profileId": django_user_client.user.profile.relay_id,
            },
            "operationName": "op_name",
        },
    )

    await client.assert_no_messages()

    message = await database_sync_to_async(send_message)(
        profile=user.profile,
        content="Hi!",
        room=room,
        user=user,
        verb=Verbs.SENT_MESSAGE,
    )

    # Check that subscription message were sent.
    resp = await client.receive(assert_id=sub_id, assert_type="next")
    assert resp["data"]["chatRoomOnMessage"]["message"]["node"]["content"] == message.content

    # Disconnect and wait the application to finish gracefully.
    await client.finalize()


@pytest.mark.asyncio
async def test_build_absolute_uri_on_graphql_subscription(
    django_user_client, graphql_ws_user_client, image_djangofile
):
    room = await database_sync_to_async(ChatRoomFactory)(created_by=django_user_client.user)
    await database_sync_to_async(ChatRoomParticipantFactory)(
        profile=django_user_client.user.profile, room=room
    )

    user = await database_sync_to_async(UserFactory)()
    user.profile.image = image_djangofile
    await user.profile.asave()
    await database_sync_to_async(ChatRoomParticipantFactory)(profile=user.profile, room=room)

    # Establish & initialize WebSocket GraphQL connection.
    client = await graphql_ws_user_client(consumer_attrs={"strict_ordering": True})

    # Subscribe to GraphQL subscription.
    sub_id = await client.send(
        msg_type="subscribe",
        payload={
            "query": textwrap.dedent(
                """
                subscription op_name($roomId: ID!, $profileId: ID!) {
                  chatRoomOnMessage(roomId: $roomId, profileId: $profileId) {
                    message {
                      node {
                        profile {
                          image(width: 100, height: 100) {
                            url
                          }
                        }
                      }
                    }
                  }
                }
                """
            ),
            "variables": {
                "roomId": room.relay_id,
                "profileId": django_user_client.user.profile.relay_id,
            },
            "operationName": "op_name",
        },
    )

    await client.assert_no_messages()

    # trigger a subscription message
    await database_sync_to_async(send_message)(
        user=user,
        profile=user.profile,
        content="Hi!",
        room=room,
        verb=Verbs.SENT_MESSAGE,
    )

    # Check that subscription message were sent.
    resp = await client.receive(assert_id=sub_id, assert_type="next")
    assert resp["data"]["chatRoomOnMessage"]["message"]["node"]["profile"]["image"][
        "url"
    ].startswith("http")

    # Disconnect and wait the application to finish gracefully.
    await client.finalize()


@pytest.mark.asyncio
async def test_user_recieves_message_count_update(django_user_client, graphql_ws_user_client):
    room = await database_sync_to_async(ChatRoomFactory)(created_by=django_user_client.user)
    await database_sync_to_async(ChatRoomParticipantFactory)(
        profile=django_user_client.user.profile, room=room
    )
    user = await database_sync_to_async(UserFactory)()
    await database_sync_to_async(ChatRoomParticipantFactory)(room=room, profile=user.profile)

    # Establish & initialize WebSocket GraphQL connection.
    client = await graphql_ws_user_client(consumer_attrs={"strict_ordering": True})

    # Subscribe to GraphQL subscription.
    sub_id = await client.send(
        msg_type="subscribe",
        payload={
            "query": textwrap.dedent(
                """
                subscription op_name($profileId: ID!) {
                  chatRoomOnMessagesCountUpdate(profileId: $profileId) {
                    profile {
                      ... on ChatRoomsInterface {
                        unreadMessagesCount
                      }
                    }
                  }
                }
                """
            ),
            "variables": {"profileId": django_user_client.user.profile.relay_id},
            "operationName": "op_name",
        },
    )

    await client.assert_no_messages()

    await database_sync_to_async(send_message)(
        user=user,
        profile=user.profile,
        content="Hi!",
        room=room,
        verb=Verbs.SENT_MESSAGE,
    )

    # Check that subscription message were sent.

    resp = await client.receive(assert_id=sub_id, assert_type="next")

    # Disconnect and wait the application to finish gracefully.
    await client.finalize()

    assert resp["data"]["chatRoomOnMessagesCountUpdate"]["profile"]["unreadMessagesCount"] == 1
