import asyncio

import pytest
import swapper
from channels.db import database_sync_to_async

from baseapp_core.strawberry.subscriptions import subscription_group
from baseapp_core.strawberry.testing import next_result, wait_for_group
from baseapp_core.tests.factories import UserFactory

from ..utils import send_message
from .factories import ChatRoomFactory, ChatRoomParticipantFactory

Message = swapper.load_model("baseapp_chats", "Message")
Verbs = Message.Verbs

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio]

ON_MESSAGE = """
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

ON_MESSAGE_WITH_PROFILE_IMAGE = """
    subscription op_name($roomId: ID!, $profileId: ID!) {
      chatRoomOnMessage(roomId: $roomId, profileId: $profileId) {
        message {
          node {
            profile {
              image(width: 100, height: 100)
            }
          }
        }
      }
    }
"""

ON_MESSAGES_COUNT_UPDATE = """
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

ON_MESSAGES_COUNT_UPDATE_WITH_ROOMS = """
    subscription op_name($profileId: ID!) {
      chatRoomOnMessagesCountUpdate(profileId: $profileId) {
        profile {
          ... on ChatRoomsInterface {
            unreadMessagesCount
            chatRooms {
              edges {
                node {
                  id
                  unreadMessages {
                    count
                    markedUnread
                  }
                }
              }
            }
          }
        }
      }
    }
"""


@database_sync_to_async
def _room_with_other_participant(user, other_image=None) -> tuple:
    room = ChatRoomFactory(created_by=user)
    ChatRoomParticipantFactory(profile=user.profile, room=room)
    other = UserFactory()
    if other_image is not None:
        other.profile.image = other_image
        other.profile.save()
    ChatRoomParticipantFactory(room=room, profile=other.profile)
    return room, other, room.relay_id, user.profile.relay_id


def _send(user, room) -> Message:
    return send_message(
        profile=user.profile, content="Hi!", room=room, user=user, verb=Verbs.SENT_MESSAGE
    )


async def test_user_recieves_news_message_subscription_event___2(
    django_user_client, graphql_ws_user_client
) -> None:
    room, other, room_id, profile_id = await _room_with_other_participant(django_user_client.user)

    async with await graphql_ws_user_client() as ws:
        result = next_result(ws, ON_MESSAGE, {"roomId": room_id, "profileId": profile_id})
        await wait_for_group(subscription_group("ChatRoomOnMessage", room_id))
        message = await database_sync_to_async(_send)(other, room)
        result = await asyncio.wait_for(result, 5)

    assert not result.errors
    assert result.data["chatRoomOnMessage"]["message"]["node"]["content"] == message.content


async def test_sender_does_not_receive_own_message_on_subscription(
    django_user_client, graphql_ws_user_client
) -> None:
    """The author of a message must not get it echoed back over their own subscription."""
    user = django_user_client.user
    room, _, room_id, profile_id = await _room_with_other_participant(user)

    async with await graphql_ws_user_client() as ws:
        result = next_result(ws, ON_MESSAGE, {"roomId": room_id, "profileId": profile_id})
        await wait_for_group(subscription_group("ChatRoomOnMessage", room_id))
        await database_sync_to_async(_send)(user, room)
        # The sender relies on the mutation response to render their own message.
        await asyncio.sleep(0.5)
        assert not result.done()
        result.cancel()


async def test_build_absolute_uri_on_graphql_subscription(
    django_user_client, graphql_ws_user_client, image_djangofile
) -> None:
    room, other, room_id, profile_id = await _room_with_other_participant(
        django_user_client.user, other_image=image_djangofile
    )

    async with await graphql_ws_user_client() as ws:
        result = next_result(
            ws, ON_MESSAGE_WITH_PROFILE_IMAGE, {"roomId": room_id, "profileId": profile_id}
        )
        await wait_for_group(subscription_group("ChatRoomOnMessage", room_id))
        await database_sync_to_async(_send)(other, room)
        result = await asyncio.wait_for(result, 5)

    assert not result.errors
    image = result.data["chatRoomOnMessage"]["message"]["node"]["profile"]["image"]
    assert image.startswith("http")


async def test_user_recieves_message_count_update(
    django_user_client, graphql_ws_user_client
) -> None:
    room, other, _, profile_id = await _room_with_other_participant(django_user_client.user)

    async with await graphql_ws_user_client() as ws:
        result = next_result(ws, ON_MESSAGES_COUNT_UPDATE, {"profileId": profile_id})
        await wait_for_group(subscription_group("ChatRoomOnMessagesCountUpdate", profile_id))
        await database_sync_to_async(_send)(other, room)
        result = await asyncio.wait_for(result, 5)

    assert not result.errors
    assert result.data["chatRoomOnMessagesCountUpdate"]["profile"]["unreadMessagesCount"] == 1


async def test_current_profile_ws_context(django_user_client, graphql_ws_user_client) -> None:
    """`unreadMessages` without `profileId` reads the Current-Profile sent on connection."""
    room, other, _, profile_id = await _room_with_other_participant(django_user_client.user)

    async with await graphql_ws_user_client() as ws:
        result = next_result(ws, ON_MESSAGES_COUNT_UPDATE_WITH_ROOMS, {"profileId": profile_id})
        await wait_for_group(subscription_group("ChatRoomOnMessagesCountUpdate", profile_id))
        await database_sync_to_async(_send)(other, room)
        result = await asyncio.wait_for(result, 5)

    assert not result.errors
    profile = result.data["chatRoomOnMessagesCountUpdate"]["profile"]
    assert profile["unreadMessagesCount"] == 1
    assert profile["chatRooms"]["edges"][0]["node"]["unreadMessages"]["count"] == 1
