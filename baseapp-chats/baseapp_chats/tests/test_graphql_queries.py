from datetime import timedelta

import pytest
from baseapp_blocks.tests.factories import BlockFactory
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory
from django.utils import timezone

from .factories import ChatRoomFactory, ChatRoomParticipantFactory, MessageFactory

pytestmark = pytest.mark.django_db


USER_ROOMS_GRAPHQL = """
    query UserRooms {
        me {
            profile {
                chatRooms {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
        }
    }
"""

ROOM_GRAPHQL = """
    query GetRoom($roomId: ID!) {
        chatRoom(id: $roomId) {
            allMessages {
                edges {
                    node {
                        id
                        content
                    }
                }
            }
        }
    }
"""

PROFILE_ROOMS_GRAPHQL = """
    query ProfileRooms($profileId: ID!, $archived: Boolean, $unreadMessages: Boolean) {
        profile(id: $profileId) {
            id
            name
            ... on ChatRoomsInterface {
                chatRooms (archived: $archived, unreadMessages: $unreadMessages) {
                    edges {
                        node {
                            id
                            unreadMessages(profileId: $profileId) {
                                count
                                markedUnread
                            }
                        }
                    }
                }
            }
        }
    }
"""


def test_user_can_list_rooms(graphql_user_client, django_user_client):
    user_profie = ProfileFactory()
    friend_profile = ProfileFactory()

    user_room = ChatRoomFactory(created_by=user_profie.owner)
    friend_room = ChatRoomFactory(created_by=friend_profile.owner)

    ChatRoomParticipantFactory(profile=user_profie, room=user_room)
    ChatRoomParticipantFactory(profile=friend_profile, room=friend_room)

    ChatRoomParticipantFactory(profile=django_user_client.user.profile, room=user_room)
    ChatRoomParticipantFactory(profile=django_user_client.user.profile, room=friend_room)

    response = graphql_user_client(
        USER_ROOMS_GRAPHQL,
        variables={},
    )

    content = response.json()

    assert len(content["data"]["me"]["profile"]["chatRooms"]["edges"]) == 2


def test_unread_messages_count(graphql_user_client, django_user_client):
    my_profile = django_user_client.user.profile
    friend_profile = ProfileFactory()
    room = ChatRoomFactory(created_by=django_user_client.user)

    ChatRoomParticipantFactory(room=room, profile=my_profile)
    ChatRoomParticipantFactory(room=room, profile=friend_profile)

    MessageFactory(room=room, profile=friend_profile)

    response = graphql_user_client(
        PROFILE_ROOMS_GRAPHQL,
        variables={"profileId": my_profile.relay_id},
    )

    content = response.json()

    assert len(content["data"]["profile"]["chatRooms"]["edges"]) == 1
    assert (
        content["data"]["profile"]["chatRooms"]["edges"][0]["node"]["unreadMessages"]["count"] == 1
    )


def test_filter_rooms_with_unread_messages(graphql_user_client, django_user_client):
    my_profile = django_user_client.user.profile
    friend_in_room_with_unread = ProfileFactory()
    friend_in_room_with_read = ProfileFactory()
    room_with_unread = ChatRoomFactory(created_by=django_user_client.user)
    room_with_read = ChatRoomFactory(created_by=django_user_client.user)

    ChatRoomParticipantFactory(room=room_with_unread, profile=my_profile)
    ChatRoomParticipantFactory(room=room_with_unread, profile=friend_in_room_with_unread)

    MessageFactory(room=room_with_unread, profile=friend_in_room_with_unread)

    ChatRoomParticipantFactory(room=room_with_read, profile=my_profile)
    ChatRoomParticipantFactory(room=room_with_read, profile=friend_in_room_with_read)

    read_message = MessageFactory(room=room_with_read, profile=friend_in_room_with_read)

    read_message.statuses.filter(profile=my_profile).update(is_read=True)

    response = graphql_user_client(
        PROFILE_ROOMS_GRAPHQL,
        variables={"profileId": my_profile.relay_id, "unreadMessages": True},
    )

    content = response.json()

    assert len(content["data"]["profile"]["chatRooms"]["edges"]) == 1
    assert (
        content["data"]["profile"]["chatRooms"]["edges"][0]["node"]["id"]
        == room_with_unread.relay_id
    )


def test_archived_chats(graphql_user_client, django_user_client):
    my_profile = django_user_client.user.profile
    friend_profile = ProfileFactory()
    room = ChatRoomFactory(created_by=django_user_client.user)

    ChatRoomParticipantFactory(room=room, profile=my_profile, has_archived_room=True)
    ChatRoomParticipantFactory(room=room, profile=friend_profile)

    response = graphql_user_client(
        PROFILE_ROOMS_GRAPHQL,
        variables={"profileId": my_profile.relay_id, "archived": True},
    )

    content = response.json()

    assert len(content["data"]["profile"]["chatRooms"]["edges"]) == 1

    response = graphql_user_client(
        PROFILE_ROOMS_GRAPHQL,
        variables={"profileId": friend_profile.relay_id, "archived": True},
    )

    content = response.json()

    assert len(content["data"]["profile"]["chatRooms"]["edges"]) == 0


def test_cant_list_rooms_if_not_participating(graphql_user_client):
    user = UserFactory()

    user_room = ChatRoomFactory(created_by=user)

    ChatRoomParticipantFactory(profile=user.profile, room=user_room)

    response = graphql_user_client(
        USER_ROOMS_GRAPHQL,
        variables={},
    )

    content = response.json()

    assert len(content["data"]["me"]["profile"]["chatRooms"]["edges"]) == 0


def test_rooms_list_are_ordered_by_last_message_time(graphql_user_client, django_user_client):
    user = UserFactory()
    user_2 = UserFactory()
    user_3 = UserFactory()

    room = ChatRoomFactory(created_by=user)
    room_2 = ChatRoomFactory(created_by=user_2, last_message_time=timezone.now())
    room_3 = ChatRoomFactory(
        created_by=user_3, last_message_time=timezone.now() - timedelta(hours=1)
    )

    ChatRoomParticipantFactory(profile=user.profile, room=room)
    ChatRoomParticipantFactory(profile=django_user_client.user.profile, room=room)
    ChatRoomParticipantFactory(profile=user_2.profile, room=room_2)
    ChatRoomParticipantFactory(profile=django_user_client.user.profile, room=room_2)
    ChatRoomParticipantFactory(profile=user_3.profile, room=room_3)
    ChatRoomParticipantFactory(profile=django_user_client.user.profile, room=room_3)

    room_id = room.relay_id
    room_2_id = room_2.relay_id
    room_3_id = room_3.relay_id

    response = graphql_user_client(
        USER_ROOMS_GRAPHQL,
        variables={},
    )

    content = response.json()

    assert len(content["data"]["me"]["profile"]["chatRooms"]["edges"]) == 3
    assert content["data"]["me"]["profile"]["chatRooms"]["edges"][0]["node"]["id"] == room_2_id
    assert content["data"]["me"]["profile"]["chatRooms"]["edges"][1]["node"]["id"] == room_id
    assert content["data"]["me"]["profile"]["chatRooms"]["edges"][2]["node"]["id"] == room_3_id


def test_can_list_messages_from_participating_room(graphql_user_client, django_user_client):
    band = ProfileFactory()
    room = ChatRoomFactory(created_by=band.owner)

    ChatRoomParticipantFactory(profile=django_user_client.user.profile, room=room)
    ChatRoomParticipantFactory(profile=band, room=room)

    message_1 = MessageFactory(room=room, profile=band)
    message_2 = MessageFactory(room=room, profile=band)

    response = graphql_user_client(ROOM_GRAPHQL, variables={"roomId": room.relay_id})

    content = response.json()

    assert len(content["data"]["chatRoom"]["allMessages"]["edges"]) == 2
    assert (
        content["data"]["chatRoom"]["allMessages"]["edges"][0]["node"]["content"]
        == message_1.content
    )
    assert (
        content["data"]["chatRoom"]["allMessages"]["edges"][1]["node"]["content"]
        == message_2.content
    )


def test_cant_list_messages_from_non_participating_room(graphql_user_client):
    user = UserFactory()
    room = ChatRoomFactory(created_by=user)

    ChatRoomParticipantFactory(profile=user.profile, room=room)

    MessageFactory(room=room, profile=user.profile)
    MessageFactory(room=room, profile=user.profile)

    response = graphql_user_client(ROOM_GRAPHQL, variables={"roomId": room.relay_id})

    content = response.json()
    assert content["data"]["chatRoom"] is None


def test_user_cant_list_rooms_if_blocked(graphql_user_client, django_user_client):
    band = ProfileFactory()
    room = ChatRoomFactory(created_by=django_user_client.user)

    ChatRoomParticipantFactory(profile=django_user_client.user.profile, room=room)
    ChatRoomParticipantFactory(profile=band, room=room)

    response = graphql_user_client(
        USER_ROOMS_GRAPHQL,
        variables={},
    )
    content = response.json()
    assert len(content["data"]["me"]["profile"]["chatRooms"]["edges"]) == 1

    BlockFactory(actor=band, target=django_user_client.user.profile)

    response = graphql_user_client(
        USER_ROOMS_GRAPHQL,
        variables={},
    )
    content = response.json()
    assert len(content["data"]["me"]["profile"]["chatRooms"]["edges"]) == 0


def test_user_can_list_rooms_that_are_not_blocked(graphql_user_client, django_user_client):
    band = ProfileFactory()
    user_2 = UserFactory()

    room = ChatRoomFactory(created_by=django_user_client.user)
    room_2 = ChatRoomFactory(created_by=user_2, last_message_time=timezone.now())

    ChatRoomParticipantFactory(profile=django_user_client.user.profile, room=room)
    ChatRoomParticipantFactory(profile=band, room=room)

    ChatRoomParticipantFactory(profile=user_2.profile, room=room_2)
    ChatRoomParticipantFactory(profile=django_user_client.user.profile, room=room_2)

    response = graphql_user_client(
        USER_ROOMS_GRAPHQL,
        variables={},
    )
    content = response.json()
    assert len(content["data"]["me"]["profile"]["chatRooms"]["edges"]) == 2

    BlockFactory(actor=django_user_client.user.profile, target=band)

    response = graphql_user_client(
        USER_ROOMS_GRAPHQL,
        variables={},
    )
    content = response.json()
    assert len(content["data"]["me"]["profile"]["chatRooms"]["edges"]) == 1


def test_user_cant_open_room_if_blocked(graphql_user_client, django_user_client):
    band = ProfileFactory()
    room = ChatRoomFactory(created_by=django_user_client.user)

    ChatRoomParticipantFactory(profile=django_user_client.user.profile, room=room)
    ChatRoomParticipantFactory(profile=band, room=room)

    response = graphql_user_client(ROOM_GRAPHQL, variables={"roomId": room.relay_id})
    content = response.json()

    assert content["data"]["chatRoom"] is not None

    BlockFactory(actor=band, target=django_user_client.user.profile)

    response = graphql_user_client(ROOM_GRAPHQL, variables={"roomId": room.relay_id})
    content = response.json()
    assert content["data"]["chatRoom"] is None
