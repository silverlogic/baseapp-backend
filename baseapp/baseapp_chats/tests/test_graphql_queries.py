from datetime import timedelta

import pytest
import swapper
from django.utils import timezone
from freezegun import freeze_time

from baseapp_blocks.tests.factories import BlockFactory
from baseapp_core.graphql.testing.fixtures import graphql_query
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import ChatRoomFactory, ChatRoomParticipantFactory, MessageFactory

pytestmark = pytest.mark.django_db

UnreadMessageCount = swapper.load_model("baseapp_chats", "UnreadMessageCount")


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
                        messageType
                    }
                }
            }
        }
    }
"""

PROFILE_ROOMS_GRAPHQL = """
    query ProfileRooms($profileId: ID!, $archived: Boolean, $unreadMessages: Boolean, $q: String) {
        profile(id: $profileId) {
            id
            name
            ... on ChatRoomsInterface {
                chatRooms (archived: $archived, unreadMessages: $unreadMessages, q: $q) {
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


def test_archived_chats(django_client):
    me = UserFactory()
    my_profile = me.profile
    friend = UserFactory()
    friend_profile = friend.profile
    room = ChatRoomFactory(created_by=me)

    ChatRoomParticipantFactory(room=room, profile=my_profile, has_archived_room=True)
    ChatRoomParticipantFactory(room=room, profile=friend_profile)

    django_client.force_login(me)
    response = graphql_query(
        PROFILE_ROOMS_GRAPHQL,
        variables={"profileId": my_profile.relay_id, "archived": True},
        client=django_client,
    )

    content = response.json()

    assert len(content["data"]["profile"]["chatRooms"]["edges"]) == 1

    django_client.force_login(friend)
    response = graphql_query(
        PROFILE_ROOMS_GRAPHQL,
        variables={"profileId": friend_profile.relay_id, "archived": True},
        client=django_client,
    )

    content = response.json()

    assert len(content["data"]["profile"]["chatRooms"]["edges"]) == 0


def test_can_filter_by_room_title(django_client):
    user_1 = UserFactory(first_name="Luke", last_name="Skywalker")
    profile_1 = user_1.profile

    user_2 = UserFactory(first_name="Darth", last_name="Vader")
    profile_2 = user_2.profile

    profile_3 = ProfileFactory(name="Tester123")
    profile_4 = ProfileFactory(name="Luke Littler")

    room_1 = ChatRoomFactory(created_by=profile_1.owner, is_group=False)
    room_2 = ChatRoomFactory(created_by=profile_1.owner, is_group=False)
    room_3 = ChatRoomFactory(created_by=profile_1.owner, title="Lucky Luke", is_group=True)
    room_4 = ChatRoomFactory(created_by=profile_2.owner, title="Star Wars", is_group=True)

    ChatRoomParticipantFactory(room=room_1, profile=profile_1)
    ChatRoomParticipantFactory(room=room_1, profile=profile_2, has_archived_room=True)

    ChatRoomParticipantFactory(room=room_2, profile=profile_1, has_archived_room=True)
    ChatRoomParticipantFactory(room=room_2, profile=profile_4)

    ChatRoomParticipantFactory(room=room_3, profile=profile_1)
    ChatRoomParticipantFactory(room=room_3, profile=profile_2)
    ChatRoomParticipantFactory(room=room_3, profile=profile_3, has_archived_room=True)

    ChatRoomParticipantFactory(room=room_4, profile=profile_1, has_archived_room=True)
    ChatRoomParticipantFactory(room=room_4, profile=profile_2)

    django_client.force_login(user_1)
    response = graphql_query(
        PROFILE_ROOMS_GRAPHQL,
        variables={"profileId": profile_1.relay_id, "q": "lUKE"},
        client=django_client,
    )
    content = response.json()

    rooms = content["data"]["profile"]["chatRooms"]["edges"]
    assert len(rooms) == 2
    room_ids = [room["node"]["id"] for room in rooms]
    assert room_1.relay_id not in room_ids  # room name 'Darth Vader'
    assert room_2.relay_id in room_ids  # room name 'Luke Littler'
    assert room_3.relay_id in room_ids  # room name 'Lucky Luke'
    assert room_4.relay_id not in room_ids  # room name 'Star Wars'

    django_client.force_login(user_2)
    response = graphql_query(
        PROFILE_ROOMS_GRAPHQL,
        variables={"profileId": profile_2.relay_id, "q": "u"},
        client=django_client,
    )
    content = response.json()

    rooms = content["data"]["profile"]["chatRooms"]["edges"]
    assert len(rooms) == 2
    room_ids = [room["node"]["id"] for room in rooms]
    assert room_1.relay_id in room_ids  # room name 'Luke Skywalker'
    assert room_2.relay_id not in room_ids  # not a member
    assert room_3.relay_id in room_ids  # room name 'Lucky Luke'
    assert room_4.relay_id not in room_ids  # room name 'Star Wars'


def test_can_filter_unread_rooms_by_title(django_client):
    user_1 = UserFactory(first_name="Luke", last_name="Skywalker (Artist)")
    profile_1 = user_1.profile
    profile_2 = ProfileFactory(name="Darth Vader")
    profile_3 = ProfileFactory(name="Han Solo")
    profile_4 = ProfileFactory(name="R2D2")

    room_1 = ChatRoomFactory(created_by=profile_2.owner, is_group=False)
    room_2 = ChatRoomFactory(created_by=profile_3.owner, is_group=False)
    room_3 = ChatRoomFactory(created_by=profile_4.owner, title="art exhibition", is_group=True)
    room_4 = ChatRoomFactory(created_by=profile_1.owner, title="Some group", is_group=True)
    room_5 = ChatRoomFactory(created_by=profile_1.owner, title="Star Wars, Part I", is_group=True)

    ChatRoomParticipantFactory(room=room_1, profile=profile_1, has_archived_room=True)
    ChatRoomParticipantFactory(room=room_1, profile=profile_2)

    ChatRoomParticipantFactory(room=room_2, profile=profile_1)
    ChatRoomParticipantFactory(room=room_2, profile=profile_4, has_archived_room=True)

    ChatRoomParticipantFactory(room=room_3, profile=profile_1)
    ChatRoomParticipantFactory(room=room_3, profile=profile_2, has_archived_room=True)
    ChatRoomParticipantFactory(room=room_3, profile=profile_3)

    ChatRoomParticipantFactory(room=room_4, profile=profile_1, has_archived_room=True)
    ChatRoomParticipantFactory(room=room_4, profile=profile_2)

    ChatRoomParticipantFactory(room=room_5, profile=profile_1)
    ChatRoomParticipantFactory(room=room_5, profile=profile_4)

    UnreadMessageCount(room=room_1, profile=profile_1, marked_unread=True).save()
    MessageFactory(room=room_2, profile=profile_4)
    MessageFactory(room=room_3, profile=profile_3)
    MessageFactory(room=room_4, profile=profile_2)
    MessageFactory(room=room_5, profile=profile_1)

    django_client.force_login(user_1)
    response = graphql_query(
        PROFILE_ROOMS_GRAPHQL,
        variables={"profileId": profile_1.relay_id, "unreadMessages": True, "q": "art"},
        client=django_client,
    )
    content = response.json()

    rooms = content["data"]["profile"]["chatRooms"]["edges"]
    assert len(rooms) == 2
    room_ids = [room["node"]["id"] for room in rooms]
    assert room_1.relay_id in room_ids  # room name 'Darth Vader'
    assert room_2.relay_id not in room_ids  # room name 'R2D2'
    assert room_3.relay_id in room_ids  # room name 'art exhibition'
    assert room_4.relay_id not in room_ids  # room name 'Some group'
    assert room_5.relay_id not in room_ids  # room name 'Star Wars, Part I', but no unread messages


def test_can_filter_archived_rooms_by_title(django_client):
    user_1 = UserFactory(first_name="Tester", last_name="11")
    profile_1 = user_1.profile
    profile_2 = ProfileFactory(name="Shrek")
    profile_3 = ProfileFactory(name="111111")
    profile_4 = ProfileFactory(name="112358")

    room_1 = ChatRoomFactory(created_by=profile_4.owner, title="11th street", is_group=True)
    room_2 = ChatRoomFactory(created_by=profile_4.owner, is_group=False)
    room_3 = ChatRoomFactory(created_by=profile_4.owner, title="10000 BC", is_group=True)
    room_4 = ChatRoomFactory(created_by=profile_4.owner, is_group=False)
    room_5 = ChatRoomFactory(created_by=profile_4.owner, title="Oceans 11", is_group=True)

    ChatRoomParticipantFactory(room=room_1, profile=profile_1)
    ChatRoomParticipantFactory(room=room_1, profile=profile_2, has_archived_room=True)
    ChatRoomParticipantFactory(room=room_1, profile=profile_4, has_archived_room=True)

    ChatRoomParticipantFactory(room=room_2, profile=profile_1, has_archived_room=True)
    ChatRoomParticipantFactory(room=room_2, profile=profile_2, has_archived_room=True)

    ChatRoomParticipantFactory(room=room_3, profile=profile_1, has_archived_room=True)
    ChatRoomParticipantFactory(room=room_3, profile=profile_2, has_archived_room=True)
    ChatRoomParticipantFactory(room=room_3, profile=profile_3, has_archived_room=True)

    ChatRoomParticipantFactory(room=room_4, profile=profile_1, has_archived_room=True)
    ChatRoomParticipantFactory(room=room_4, profile=profile_3)

    ChatRoomParticipantFactory(room=room_5, profile=profile_1, has_archived_room=True)
    ChatRoomParticipantFactory(room=room_5, profile=profile_3)

    MessageFactory(room=room_2, profile=profile_4)
    MessageFactory(room=room_5, profile=profile_3)

    django_client.force_login(user_1)
    response = graphql_query(
        PROFILE_ROOMS_GRAPHQL,
        variables={"profileId": profile_1.relay_id, "archived": True, "q": "11"},
        client=django_client,
    )
    content = response.json()

    rooms = content["data"]["profile"]["chatRooms"]["edges"]
    assert len(rooms) == 2
    room_ids = [room["node"]["id"] for room in rooms]
    assert room_1.relay_id not in room_ids  # room name '11th street' but not archived
    assert room_2.relay_id not in room_ids  # room name 'Shrek'
    assert room_3.relay_id not in room_ids  # room name '10000 BC'
    assert room_4.relay_id in room_ids  # room name '112358'
    assert room_5.relay_id in room_ids  # room name 'Oceans 11'


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


def test_new_participant_cant_list_previous_messages_when_joining_group_room(
    graphql_user_client, django_user_client, django_client
):
    with freeze_time("2024-12-01 10:00:00") as frozen_time:
        existing_profile_1 = ProfileFactory()
        existing_profile_2 = ProfileFactory()
        room = ChatRoomFactory(created_by=existing_profile_1.owner, participants_count=2)

        ChatRoomParticipantFactory(
            profile=existing_profile_1, room=room, accepted_at=timezone.now()
        )
        ChatRoomParticipantFactory(
            profile=existing_profile_2, room=room, accepted_at=timezone.now()
        )

        MessageFactory(room=room, profile=existing_profile_1)
        MessageFactory(room=room, profile=existing_profile_2)

        frozen_time.move_to(timezone.now() + timedelta(hours=1, minutes=5))

        ChatRoomParticipantFactory(
            profile=django_user_client.user.profile, room=room, accepted_at=timezone.now()
        )
        room.participants_count = 3
        room.is_group = True
        room.save()
        room.refresh_from_db()

        MessageFactory(room=room, profile=existing_profile_1)
        MessageFactory(room=room, profile=existing_profile_2)

        response = graphql_user_client(ROOM_GRAPHQL, variables={"roomId": room.relay_id})

        content = response.json()

        assert len(content["data"]["chatRoom"]["allMessages"]["edges"]) == 2

        django_client.force_login(existing_profile_1.owner)

        response = graphql_query(
            ROOM_GRAPHQL, variables={"roomId": room.relay_id}, client=django_client
        )

        content = response.json()

        assert len(content["data"]["chatRoom"]["allMessages"]["edges"]) == 4
