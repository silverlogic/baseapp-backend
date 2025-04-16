import pytest
import swapper
from django.test.client import MULTIPART_CONTENT

from baseapp_blocks.tests.factories import BlockFactory
from baseapp_core.graphql.testing.fixtures import graphql_query
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import ChatRoomFactory, ChatRoomParticipantFactory, MessageFactory
from .test_graphql_queries import PROFILE_ROOMS_GRAPHQL, ROOM_GRAPHQL

pytestmark = pytest.mark.django_db

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
Message = swapper.load_model("baseapp_chats", "Message")
ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")
UnreadMessageCount = swapper.load_model("baseapp_chats", "UnreadMessageCount")
MessageStatus = swapper.load_model("baseapp_chats", "MessageStatus")


SEND_MESSAGE_GRAPHQL = """
    mutation SendMessageMutation($input: ChatRoomSendMessageInput!) {
        chatRoomSendMessage(input: $input) {
            message {
                node {
                    id
                    content
                    inReplyTo {
                        id
                    }
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""

CREATE_ROOM_GRAPHQL = """
    mutation CreateRoomMutation($input: ChatRoomCreateInput!) {
        chatRoomCreate(input: $input) {
            room {
                node {
                    id
                    title
                    isGroup
                    participantsCount
                    participants {
                        edges {
                            node {
                                id
                            }
                        }
                    }
                    image(width: 100, height: 100) {
                        url
                    }
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
            errors {
                field
                messages
            }
        }
    }
"""

UPDATE_ROOM_GRAPHQL = """
    mutation UpdateRoomMutation($input: ChatRoomUpdateInput!) {
        chatRoomUpdate(input: $input) {
            room {
                node {
                    id
                    title
                    isGroup
                    participantsCount
                    participants {
                        edges {
                            node {
                                id
                                profile {
                                    id
                                }
                            }
                        }
                    }
                    image(width: 100, height: 100) {
                        url
                    }
                }
            }
            removedParticipants {
                id
                profile {
                    id
                }
            }
            addedParticipants {
                id
                profile {
                    id
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""

EDIT_MESSAGE_GRAPHQL = """
    mutation EditMessageMutation($input: ChatRoomEditMessageInput!) {
        chatRoomEditMessage(input: $input) {
            message {
                node {
                    id
                    content
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""

READ_MESSAGE_GRAPHQL = """
    mutation ReadMessageMutation($input: ChatRoomReadMessagesInput!) {
        chatRoomReadMessages(input: $input) {
            room {
                id
                unreadMessages {
                    count
                    markedUnread
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""

UNREAD_CHAT_GRAPHQL = """
    mutation UnreadMutation($input: ChatRoomUnreadInput!) {
        chatRoomUnread(input: $input) {
            room {
                id
                unreadMessages {
                    count
                    markedUnread
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""

ARCHIVE_CHAT_ROOM_GRAPHQL = """
    mutation ChatRoomArchiveMutation($input: ChatRoomArchiveInput!) {
        chatRoomArchive(input: $input) {
            room {
                id
            }
            errors {
                field
                messages
            }
        }
    }
"""

DELETE_MESSAGE_GRAPHQL = """
    mutation DeleteMessageMutation($input: ChatRoomDeleteMessageInput!) {
        chatRoomDeleteMessage(input: $input) {
            deletedMessage {
                node {
                    id
                    deleted
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""


def test_user_can_read_all_messages(graphql_user_client, django_user_client):
    room = ChatRoomFactory(created_by=django_user_client.user)

    my_profile = django_user_client.user.profile

    friend = ProfileFactory()
    ChatRoomParticipantFactory(room=room, profile=my_profile)
    friend_participant = ChatRoomParticipantFactory(room=room, profile=friend)

    MessageFactory.create_batch(2, room=room, profile=my_profile, user=my_profile.owner)
    MessageFactory.create_batch(
        2, room=room, profile=friend_participant.profile, user=friend_participant.profile.owner
    )

    assert MessageStatus.objects.filter(profile=my_profile, is_read=False).count() == 2
    assert (
        MessageStatus.objects.filter(profile=friend_participant.profile, is_read=False).count() == 2
    )

    # makes sure the cached field is increased when a participant send a message
    assert UnreadMessageCount.objects.filter(profile=my_profile, room=room).first().count == 2
    assert (
        UnreadMessageCount.objects.filter(profile=friend_participant.profile, room=room)
        .first()
        .count
        == 2
    )

    response = graphql_user_client(
        READ_MESSAGE_GRAPHQL,
        variables={
            "input": {
                "roomId": room.relay_id,
                "profileId": my_profile.relay_id,
            },
        },
    )
    content = response.json()

    assert content["data"]["chatRoomReadMessages"]["room"]["id"] == room.relay_id
    assert MessageStatus.objects.filter(profile=my_profile, is_read=False).count() == 0
    assert MessageStatus.objects.filter(profile=my_profile, is_read=True).count() == 4
    assert (
        MessageStatus.objects.filter(profile=friend_participant.profile, is_read=False).count() == 2
    )

    assert (
        UnreadMessageCount.objects.filter(profile=friend_participant.profile, room=room)
        .first()
        .count
        == 2
    )
    # makes sure the cached field is decreased when a participant read a message
    assert content["data"]["chatRoomReadMessages"]["room"]["unreadMessages"]["count"] == 0
    assert UnreadMessageCount.objects.filter(profile=my_profile, room=room).first().count == 0


def test_user_can_read_one_message(graphql_user_client, django_user_client):
    room = ChatRoomFactory(created_by=django_user_client.user)

    my_profile = django_user_client.user.profile

    friend = ProfileFactory()
    ChatRoomParticipantFactory(room=room, profile=my_profile)
    friend_participant = ChatRoomParticipantFactory(room=room, profile=friend)

    MessageFactory.create_batch(2, room=room, profile=my_profile, user=my_profile.owner)
    friend_messages = MessageFactory.create_batch(
        2, room=room, profile=friend_participant.profile, user=friend_participant.profile.owner
    )
    message = friend_messages[0]

    assert MessageStatus.objects.filter(profile=my_profile, is_read=False).count() == 2
    assert (
        MessageStatus.objects.filter(profile=friend_participant.profile, is_read=False).count() == 2
    )

    # makes sure the cached field is increased when a participant send a message
    assert UnreadMessageCount.objects.filter(profile=my_profile, room=room).first().count == 2
    assert (
        UnreadMessageCount.objects.filter(profile=friend_participant.profile, room=room)
        .first()
        .count
        == 2
    )

    response = graphql_user_client(
        READ_MESSAGE_GRAPHQL,
        variables={
            "input": {
                "roomId": room.relay_id,
                "profileId": my_profile.relay_id,
                "messageIds": [message.relay_id],
            },
        },
    )
    content = response.json()

    assert content["data"]["chatRoomReadMessages"]["room"]["id"] == room.relay_id
    assert MessageStatus.objects.filter(profile=my_profile, is_read=False).count() == 1
    assert MessageStatus.objects.filter(profile=my_profile, is_read=True).count() == 3
    assert (
        MessageStatus.objects.filter(profile=friend_participant.profile, is_read=False).count() == 2
    )

    assert (
        UnreadMessageCount.objects.filter(profile=friend_participant.profile, room=room)
        .first()
        .count
        == 2
    )
    # makes sure the cached field is decreased when a participant read a message
    assert content["data"]["chatRoomReadMessages"]["room"]["unreadMessages"]["count"] == 1
    assert UnreadMessageCount.objects.filter(profile=my_profile, room=room).first().count == 1


def test_user_can_unread_chat(graphql_user_client, django_user_client):
    room = ChatRoomFactory(created_by=django_user_client.user)

    my_profile = django_user_client.user.profile

    ChatRoomParticipantFactory(room=room, profile=my_profile)
    MessageFactory.create_batch(2, room=room, profile=my_profile, user=my_profile.owner)

    # Unread chat and check it is marked unread
    response = graphql_user_client(
        UNREAD_CHAT_GRAPHQL,
        variables={
            "input": {
                "roomId": room.relay_id,
                "profileId": my_profile.relay_id,
            },
        },
    )
    content = response.json()
    assert content["data"]["chatRoomUnread"]["room"]["id"] == room.relay_id
    assert content["data"]["chatRoomUnread"]["room"]["unreadMessages"]["markedUnread"] is True
    assert (
        UnreadMessageCount.objects.filter(profile=my_profile, room=room).first().marked_unread
        is True
    )

    # Read chat and check the unread mark is removed
    response = graphql_user_client(
        READ_MESSAGE_GRAPHQL,
        variables={
            "input": {
                "roomId": room.relay_id,
                "profileId": my_profile.relay_id,
            },
        },
    )
    content = response.json()
    assert content["data"]["chatRoomReadMessages"]["room"]["id"] == room.relay_id
    assert (
        content["data"]["chatRoomReadMessages"]["room"]["unreadMessages"]["markedUnread"] is False
    )
    assert (
        UnreadMessageCount.objects.filter(profile=my_profile, room=room).first().marked_unread
        is False
    )


@pytest.mark.celery_app
def test_user_can_send_message(django_user_client, graphql_user_client, celery_config):
    user = django_user_client.user
    room = ChatRoomFactory(created_by=user)
    friend = ProfileFactory()

    ChatRoomParticipantFactory(profile=user.profile, room=room)
    ChatRoomParticipantFactory(profile=friend, room=room)

    response = graphql_user_client(
        SEND_MESSAGE_GRAPHQL,
        variables={
            "input": {
                "roomId": room.relay_id,
                "profileId": user.profile.relay_id,
                "content": "blablabla",
            }
        },
    )

    content = response.json()

    assert content["data"]["chatRoomSendMessage"]["message"]["node"]["content"] == "blablabla"
    # check if message status is created for both participants
    assert MessageStatus.objects.filter(profile=user.profile, is_read=False).count() == 0
    assert MessageStatus.objects.filter(profile=friend, is_read=False).count() == 1
    room.refresh_from_db()
    assert room.messages.count() == 1


@pytest.mark.celery_app
def test_user_can_send_message_in_reply_to(django_user_client, graphql_user_client, celery_config):
    user = django_user_client.user
    room = ChatRoomFactory(created_by=user)
    friend = ProfileFactory()

    ChatRoomParticipantFactory(profile=user.profile, room=room)
    ChatRoomParticipantFactory(profile=friend, room=room)

    message = MessageFactory(room=room, profile=friend, user=friend.owner)

    response = graphql_user_client(
        SEND_MESSAGE_GRAPHQL,
        variables={
            "input": {
                "roomId": room.relay_id,
                "profileId": user.profile.relay_id,
                "content": "blablabla",
                "inReplyToId": message.relay_id,
            }
        },
    )

    content = response.json()
    assert (
        content["data"]["chatRoomSendMessage"]["message"]["node"]["inReplyTo"]["id"]
        == message.relay_id
    )


def test_cant_send_message_non_participating_room(django_user_client, graphql_user_client):
    user = UserFactory()
    room = ChatRoomFactory(created_by=user)
    ChatRoomParticipantFactory(profile=user.profile, room=room)

    response = graphql_user_client(
        SEND_MESSAGE_GRAPHQL,
        variables={
            "input": {
                "roomId": room.relay_id,
                "profileId": django_user_client.user.profile.relay_id,
                "content": "blablabla",
            }
        },
    )

    content = response.json()

    assert (
        content["data"]["chatRoomSendMessage"]["errors"][0]["messages"][0]
        == "You don't have permission to send a message in this room"
    )
    room.refresh_from_db()
    assert room.messages.count() == 0


def test_user_can_edit_message(django_user_client, graphql_user_client):
    user = django_user_client.user
    room = ChatRoomFactory(created_by=user)
    friend = ProfileFactory()

    ChatRoomParticipantFactory(profile=user.profile, room=room)
    ChatRoomParticipantFactory(profile=friend, room=room)

    message = MessageFactory(room=room, profile=user.profile, user=user)

    response = graphql_user_client(
        EDIT_MESSAGE_GRAPHQL,
        variables={
            "input": {
                "id": message.relay_id,
                "content": "edited",
            }
        },
    )

    content = response.json()

    assert content["data"]["chatRoomEditMessage"]["message"]["node"]["content"] == "edited"


def test_user_cant_edit_to_empty_message(django_user_client, graphql_user_client):
    user = django_user_client.user
    room = ChatRoomFactory(created_by=user)
    friend = ProfileFactory()

    ChatRoomParticipantFactory(profile=user.profile, room=room)
    ChatRoomParticipantFactory(profile=friend, room=room)

    message = MessageFactory(room=room, profile=user.profile, user=user)

    response = graphql_user_client(
        EDIT_MESSAGE_GRAPHQL,
        variables={
            "input": {
                "id": message.relay_id,
                "content": "",
            }
        },
    )

    content = response.json()

    assert (
        content["data"]["chatRoomEditMessage"]["errors"][0]["messages"][0]
        == "You cannot edit an empty message"
    )


def test_user_cant_edit_to_more_than_1000_caracters(django_user_client, graphql_user_client):
    user = django_user_client.user
    room = ChatRoomFactory(created_by=user)
    friend = ProfileFactory()

    ChatRoomParticipantFactory(profile=user.profile, room=room)
    ChatRoomParticipantFactory(profile=friend, room=room)

    message = MessageFactory(room=room, profile=user.profile, user=user)

    response = graphql_user_client(
        EDIT_MESSAGE_GRAPHQL,
        variables={
            "input": {
                "id": message.relay_id,
                "content": "a" * 1001,
            }
        },
    )

    content = response.json()

    assert (
        content["data"]["chatRoomEditMessage"]["errors"][0]["messages"][0]
        == "Message must be no longer than 1000 characters"
    )


def test_user_cant_edit_a_message_that_does_not_exist(django_user_client, graphql_user_client):
    user = django_user_client.user
    response = graphql_user_client(
        EDIT_MESSAGE_GRAPHQL,
        variables={
            "input": {
                "id": user.relay_id,
                "content": "edited",
            }
        },
    )

    content = response.json()

    assert (
        content["data"]["chatRoomEditMessage"]["errors"][0]["messages"][0]
        == "Message does not exist"
    )


def test_current_profile_connot_edit_message_sent_by_another_profile(
    django_user_client, graphql_user_client
):
    user = django_user_client.user
    room = ChatRoomFactory(created_by=user)
    friend = ProfileFactory()

    ChatRoomParticipantFactory(profile=user.profile, room=room)
    ChatRoomParticipantFactory(profile=friend, room=room)

    message = MessageFactory(room=room, profile=friend, user=friend.owner)

    response = graphql_user_client(
        EDIT_MESSAGE_GRAPHQL,
        variables={
            "input": {
                "id": message.relay_id,
                "content": "edited",
            }
        },
    )

    content = response.json()

    assert (
        content["data"]["chatRoomEditMessage"]["errors"][0]["messages"][0]
        == "You don't have permission to update this message"
    )


def test_user_can_create_room(django_user_client, graphql_user_client):
    band = ProfileFactory()

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "participants": [
                    band.relay_id,
                ],
            }
        },
    )

    content = response.json()

    assert content["data"]["chatRoomCreate"]["room"]["node"]["id"]
    assert len(content["data"]["chatRoomCreate"]["room"]["node"]["participants"]["edges"]) == 2


@pytest.mark.skip(reason="in-app notification is currently turned off")
@pytest.mark.celery_app
def test_user_get_new_message_in_app_notification(
    django_user_client, graphql_user_client, celery_config
):
    room = ChatRoomFactory(created_by=django_user_client.user)
    ChatRoomParticipantFactory(profile=django_user_client.user.profile, room=room)
    friend = ChatRoomParticipantFactory(room=room)

    graphql_user_client(
        SEND_MESSAGE_GRAPHQL,
        variables={
            "input": {
                "roomId": room.relay_id,
                "profileId": django_user_client.user.profile.relay_id,
                "content": "blablabla",
            }
        },
    )

    notification = friend.profile.owner.notifications.get()
    assert notification.verb == "NEW_CHAT_MESSAGE"


def test_user_cant_send_message_to_blocked_user(django_user_client, graphql_user_client):
    room = ChatRoomFactory(created_by=django_user_client.user)
    user = UserFactory()

    ChatRoomParticipantFactory(profile=django_user_client.user.profile, room=room)
    ChatRoomParticipantFactory(profile=user.profile, room=room)

    BlockFactory(actor=user.profile, target=django_user_client.user.profile)

    response = graphql_user_client(
        SEND_MESSAGE_GRAPHQL,
        variables={
            "input": {
                "roomId": room.relay_id,
                "profileId": django_user_client.user.profile.relay_id,
                "content": "blablabla",
            }
        },
    )

    content = response.json()
    assert (
        content["data"]["chatRoomSendMessage"]["errors"][0]["messages"][0]
        == "You don't have permission to send a message in this room"
    )
    assert room.messages.count() == 0


def test_blocked_user_cant_send_message_to_user(django_user_client, graphql_user_client):
    room = ChatRoomFactory(created_by=django_user_client.user)
    user = UserFactory()

    ChatRoomParticipantFactory(profile=django_user_client.user.profile, room=room)
    ChatRoomParticipantFactory(profile=user.profile, room=room)

    BlockFactory(actor=django_user_client.user.profile, target=user.profile)

    response = graphql_user_client(
        SEND_MESSAGE_GRAPHQL,
        variables={
            "input": {
                "roomId": room.relay_id,
                "profileId": django_user_client.user.profile.relay_id,
                "content": "blablabla",
            }
        },
    )

    content = response.json()
    assert (
        content["data"]["chatRoomSendMessage"]["errors"][0]["messages"][0]
        == "You don't have permission to send a message in this room"
    )
    assert room.messages.count() == 0


def test_user_cant_create_room_with_blocked_user(django_user_client, graphql_user_client):
    user = UserFactory()

    BlockFactory(actor=django_user_client.user.profile, target=user.profile)

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "participants": [
                    user.profile.relay_id,
                ],
            }
        },
    )

    content = response.json()

    assert (
        content["data"]["chatRoomCreate"]["errors"][0]["messages"][0]
        == "You can't create a chatroom with those participants"
    )


def test_blocked_user_cant_create_room_with_user(django_user_client, graphql_user_client):
    friend = ProfileFactory()

    BlockFactory(actor=friend, target=django_user_client.user.profile)

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "participants": [
                    friend.relay_id,
                ],
            }
        },
    )

    content = response.json()

    # since we use get_obj_from_relay_id which uses ObjectType.get_node it will return None for the participant that is blocked
    assert (
        content["data"]["chatRoomCreate"]["errors"][0]["messages"][0]
        == "You can't create a chatroom with those participants"
    )


@pytest.mark.celery_app
def test_user_can_archive_chatroom(django_user_client, graphql_user_client, celery_config):
    user = django_user_client.user
    room = ChatRoomFactory(created_by=user)
    friend = ProfileFactory()

    ChatRoomParticipantFactory(profile=user.profile, room=room)
    ChatRoomParticipantFactory(profile=friend, room=room)

    # Archive chatroom and query to verify
    response = graphql_user_client(
        ARCHIVE_CHAT_ROOM_GRAPHQL,
        variables={
            "input": {
                "roomId": room.relay_id,
                "profileId": user.profile.relay_id,
                "archive": True,
            }
        },
    )

    content = response.json()

    assert content["data"]["chatRoomArchive"]["room"]["id"] == room.relay_id

    response = graphql_user_client(
        PROFILE_ROOMS_GRAPHQL,
        variables={"profileId": user.profile.relay_id, "archived": True},
    )

    content = response.json()

    assert len(content["data"]["profile"]["chatRooms"]["edges"]) == 1

    # Unarchive chatroom and query to verify
    graphql_user_client(
        ARCHIVE_CHAT_ROOM_GRAPHQL,
        variables={
            "input": {
                "roomId": room.relay_id,
                "profileId": user.profile.relay_id,
                "archive": False,
            }
        },
    )

    response = graphql_user_client(
        PROFILE_ROOMS_GRAPHQL,
        variables={"profileId": user.profile.relay_id, "archived": True},
    )

    content = response.json()

    assert len(content["data"]["profile"]["chatRooms"]["edges"]) == 0


def test_user_can_create_group(django_user_client, graphql_user_client, image_djangofile):
    participant = ProfileFactory()
    participant_2 = ProfileFactory()
    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "isGroup": True,
                "title": "group",
                "participants": [
                    participant.relay_id,
                    participant_2.relay_id,
                ],
            }
        },
        content_type=MULTIPART_CONTENT,
        extra={"image": image_djangofile},
    )

    content = response.json()

    assert content["data"]["chatRoomCreate"]["room"]["node"]["id"]
    assert content["data"]["chatRoomCreate"]["room"]["node"]["title"] == "group"
    assert content["data"]["chatRoomCreate"]["room"]["node"]["isGroup"]
    assert len(content["data"]["chatRoomCreate"]["room"]["node"]["participants"]["edges"]) == 3
    assert content["data"]["chatRoomCreate"]["room"]["node"]["image"]["url"].startswith("http://")


def test_user_cant_create_group_without_title(django_user_client, graphql_user_client):
    friend = ProfileFactory()
    friend_2 = ProfileFactory()

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "isGroup": True,
                "participants": [
                    friend.relay_id,
                    friend_2.relay_id,
                ],
            }
        },
    )

    content = response.json()

    assert (
        content["data"]["chatRoomCreate"]["errors"][0]["messages"][0]
        == "Title is required for group chats"
    )


def test_create_room_handles_corrupted_images(
    django_user_client, graphql_user_client, corrupted_image
):
    friend = ProfileFactory()

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "participants": [
                    friend.relay_id,
                ],
            }
        },
        content_type=MULTIPART_CONTENT,
        extra={"image": corrupted_image},
    )

    content = response.json()
    assert "corrupted" in content["data"]["chatRoomCreate"]["errors"][0]["messages"][0]


def test_create_room_creates_system_message(django_user_client, graphql_user_client, django_client):
    friend = UserFactory()

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "participants": [
                    friend.profile.relay_id,
                ],
                "isGroup": True,
                "title": "A test group",
            }
        },
    )

    content = response.json()
    assert len(content["data"]["chatRoomCreate"]["room"]["node"]["allMessages"]["edges"]) == 1
    assert (
        content["data"]["chatRoomCreate"]["room"]["node"]["allMessages"]["edges"][0]["node"][
            "messageType"
        ]
        == "SYSTEM_GENERATED"
    )
    assert (
        content["data"]["chatRoomCreate"]["room"]["node"]["allMessages"]["edges"][0]["node"][
            "content"
        ]
        == 'You created group "A test group"'
    )
    room_id = content["data"]["chatRoomCreate"]["room"]["node"]["id"]

    django_client.force_login(friend)
    response = graphql_query(
        ROOM_GRAPHQL,
        variables={"profileId": friend.profile.relay_id, "roomId": room_id},
        client=django_client,
    )

    content = response.json()
    assert len(content["data"]["chatRoom"]["allMessages"]["edges"]) == 1
    assert (
        content["data"]["chatRoom"]["allMessages"]["edges"][0]["node"]["messageType"]
        == "SYSTEM_GENERATED"
    )
    assert (
        content["data"]["chatRoom"]["allMessages"]["edges"][0]["node"]["content"]
        == django_user_client.user.profile.name + ' created group "A test group"'
    )


def test_member_user_cannot_update_group(django_user_client, graphql_user_client, django_client):
    friend = ProfileFactory()
    friend_2 = ProfileFactory()

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "isGroup": True,
                "title": "group",
                "participants": [
                    friend.relay_id,
                    friend_2.relay_id,
                ],
            }
        },
    )
    content = response.json()
    room_id = content["data"]["chatRoomCreate"]["room"]["node"]["id"]
    django_client.force_login(friend.owner)

    response = graphql_query(
        UPDATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": friend.relay_id,
                "roomId": room_id,
                "title": "new group",
            }
        },
        client=django_client,
    )
    content = response.json()
    assert (
        content["data"]["chatRoomUpdate"]["errors"][0]["messages"][0]
        == "You don't have permission to update this room"
    )


def test_admin_user_can_update_group_title(django_user_client, graphql_user_client):
    friend = ProfileFactory()
    friend_2 = ProfileFactory()

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "isGroup": True,
                "title": "group",
                "participants": [
                    friend.relay_id,
                    friend_2.relay_id,
                ],
            }
        },
    )
    content = response.json()
    room_id = content["data"]["chatRoomCreate"]["room"]["node"]["id"]
    assert content["data"]["chatRoomCreate"]["room"]["node"]["title"] == "group"

    response = graphql_user_client(
        UPDATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "roomId": room_id,
                "title": "new group",
            }
        },
    )
    content = response.json()
    assert content["data"]["chatRoomUpdate"]["room"]["node"]["title"] == "new group"


def test_user_cannot_update_room_title(django_user_client, graphql_user_client):
    # user can't update the title of a room that is not a group
    friend = ProfileFactory()

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "isGroup": False,
                "title": "group",
                "participants": [
                    friend.relay_id,
                ],
            }
        },
    )

    content = response.json()
    room_id = content["data"]["chatRoomCreate"]["room"]["node"]["id"]

    response = graphql_user_client(
        UPDATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "roomId": room_id,
                "title": "test",
            }
        },
    )
    content = response.json()
    assert (
        content["data"]["chatRoomUpdate"]["errors"][0]["messages"][0]
        == "This room cannot be updated"
    )


def test_admin_user_can_update_group_image(
    django_user_client, graphql_user_client, image_djangofile
):
    friend = ProfileFactory()
    friend_2 = ProfileFactory()

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "isGroup": True,
                "title": "group",
                "participants": [
                    friend.relay_id,
                    friend_2.relay_id,
                ],
            }
        },
    )

    content = response.json()
    room_id = content["data"]["chatRoomCreate"]["room"]["node"]["id"]
    assert content["data"]["chatRoomCreate"]["room"]["node"]["image"] is None

    response = graphql_user_client(
        UPDATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "roomId": room_id,
            }
        },
        content_type=MULTIPART_CONTENT,
        extra={"image": image_djangofile},
    )
    content = response.json()
    assert content["data"]["chatRoomUpdate"]["room"]["node"]["image"]["url"].startswith("http://")


def test_admin_user_can_delete_group_image(
    django_user_client, graphql_user_client, image_djangofile
):
    # user can delete the image of a group if he is the creator/admin
    friend = ProfileFactory()
    friend_2 = ProfileFactory()

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "isGroup": True,
                "title": "group",
                "participants": [
                    friend.relay_id,
                    friend_2.relay_id,
                ],
            }
        },
        content_type=MULTIPART_CONTENT,
        extra={"image": image_djangofile},
    )

    content = response.json()
    room_id = content["data"]["chatRoomCreate"]["room"]["node"]["id"]
    assert content["data"]["chatRoomCreate"]["room"]["node"]["image"] is not None

    response = graphql_user_client(
        UPDATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "roomId": room_id,
                "deleteImage": True,
            }
        },
    )
    content = response.json()
    assert content["data"]["chatRoomUpdate"]["room"]["node"]["image"] is None


def test_update_room_handles_corrupted_images(
    django_user_client, graphql_user_client, corrupted_image
):
    friend = ProfileFactory()

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "isGroup": True,
                "title": "group",
                "participants": [
                    friend.relay_id,
                ],
            }
        },
    )

    content = response.json()
    room_id = content["data"]["chatRoomCreate"]["room"]["node"]["id"]

    response = graphql_user_client(
        UPDATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "roomId": room_id,
            }
        },
        content_type=MULTIPART_CONTENT,
        extra={"image": corrupted_image},
    )

    content = response.json()
    assert "corrupted" in content["data"]["chatRoomUpdate"]["errors"][0]["messages"][0]


def test_admin_user_can_remove_participants(django_user_client, graphql_user_client):
    friend_1 = ProfileFactory()
    friend_2 = ProfileFactory()
    friend_3 = ProfileFactory()
    friend_4 = ProfileFactory()

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "isGroup": True,
                "title": "group",
                "participants": [
                    friend_1.relay_id,
                    friend_2.relay_id,
                    friend_3.relay_id,
                    friend_4.relay_id,
                ],
            }
        },
    )
    content = response.json()
    room_id = content["data"]["chatRoomCreate"]["room"]["node"]["id"]
    assert content["data"]["chatRoomCreate"]["room"]["node"]["participantsCount"] == 5

    response = graphql_user_client(
        UPDATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "roomId": room_id,
                "removeParticipants": [friend_3.relay_id, friend_4.relay_id],
            }
        },
    )
    content = response.json()
    assert content["data"]["chatRoomUpdate"]["room"]["node"]["title"] == "group"
    assert content["data"]["chatRoomUpdate"]["room"]["node"]["participantsCount"] == 3

    participants = content["data"]["chatRoomUpdate"]["room"]["node"]["participants"]["edges"]
    assert len(participants) == 3
    ids = [participant["node"]["profile"]["id"] for participant in participants]
    assert friend_1.relay_id in ids
    assert friend_2.relay_id in ids
    assert friend_3.relay_id not in ids
    assert friend_4.relay_id not in ids

    removed_participants = content["data"]["chatRoomUpdate"]["removedParticipants"]
    assert len(removed_participants) == 2
    ids = [participant["profile"]["id"] for participant in removed_participants]
    assert friend_1.relay_id not in ids
    assert friend_2.relay_id not in ids
    assert friend_3.relay_id in ids
    assert friend_4.relay_id in ids


def test_member_user_can_leave_room(django_user_client, graphql_user_client, django_client):
    friend_1 = ProfileFactory()
    friend_2 = ProfileFactory()
    friend_3 = ProfileFactory()

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "isGroup": True,
                "title": "group",
                "participants": [
                    friend_1.relay_id,
                    friend_2.relay_id,
                    friend_3.relay_id,
                ],
            }
        },
    )
    content = response.json()
    room_id = content["data"]["chatRoomCreate"]["room"]["node"]["id"]

    django_client.force_login(friend_3.owner)

    response = graphql_query(
        UPDATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": friend_3.relay_id,
                "roomId": room_id,
                "removeParticipants": [friend_3.relay_id],
            }
        },
        client=django_client,
    )
    content = response.json()
    assert content["data"]["chatRoomUpdate"]["room"]["node"]["title"] == "group"
    participants_ids = [
        participant["node"]["profile"]["id"]
        for participant in content["data"]["chatRoomUpdate"]["room"]["node"]["participants"][
            "edges"
        ]
    ]
    assert len(participants_ids) == 3
    assert friend_3.relay_id not in participants_ids


def test_member_user_cannot_remove_other_members(
    django_user_client, graphql_user_client, django_client
):
    friend_1 = ProfileFactory()
    friend_2 = ProfileFactory()
    friend_3 = ProfileFactory()

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "isGroup": True,
                "title": "group",
                "participants": [
                    friend_1.relay_id,
                    friend_2.relay_id,
                    friend_3.relay_id,
                ],
            }
        },
    )
    content = response.json()
    room_id = content["data"]["chatRoomCreate"]["room"]["node"]["id"]
    django_client.force_login(friend_3.owner)

    response = graphql_query(
        UPDATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": friend_3.relay_id,
                "roomId": room_id,
                "removeParticipants": [friend_2.relay_id, friend_3.relay_id],
            }
        },
        client=django_client,
    )
    content = response.json()
    assert (
        content["data"]["chatRoomUpdate"]["errors"][0]["messages"][0]
        == "You don't have permission to update this room"
    )


def test_user_can_delete_own_message(graphql_user_client, django_user_client):
    room = ChatRoomFactory(created_by=django_user_client.user)

    my_profile = django_user_client.user.profile

    ChatRoomParticipantFactory(room=room, profile=my_profile)
    my_messages = MessageFactory.create_batch(
        2, room=room, profile=my_profile, user=my_profile.owner
    )

    # Unread chat and check it is marked unread
    response = graphql_user_client(
        DELETE_MESSAGE_GRAPHQL,
        variables={
            "input": {
                "id": my_messages[0].relay_id,
            },
        },
    )

    my_messages[0].refresh_from_db()
    my_messages[1].refresh_from_db()
    content = response.json()
    assert (
        content["data"]["chatRoomDeleteMessage"]["deletedMessage"]["node"]["id"]
        == my_messages[0].relay_id
    )
    assert content["data"]["chatRoomDeleteMessage"]["deletedMessage"]["node"]["deleted"] is True
    assert my_messages[0].deleted is True
    assert my_messages[1].deleted is False


def test_user_cant_delete_other_users_message(graphql_user_client, django_user_client):
    room = ChatRoomFactory(created_by=django_user_client.user)

    my_profile = django_user_client.user.profile

    ChatRoomParticipantFactory(room=room, profile=my_profile)
    other_participant = ChatRoomParticipantFactory(room=room)
    other_users_messages = MessageFactory.create_batch(
        2, room=room, profile=other_participant.profile, user=other_participant.profile.owner
    )

    # Unread chat and check it is marked unread
    response = graphql_user_client(
        DELETE_MESSAGE_GRAPHQL,
        variables={
            "input": {
                "id": other_users_messages[0].relay_id,
            },
        },
    )
    content = response.json()
    assert (
        content["data"]["chatRoomDeleteMessage"]["errors"][0]["messages"][0]
        == "You don't have permission to update this message"
    )


def test_admin_user_can_add_members_to_group(django_user_client, graphql_user_client):
    friend_1 = ProfileFactory()
    friend_2 = ProfileFactory()
    friend_3 = ProfileFactory()

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "isGroup": True,
                "title": "group",
                "participants": [
                    friend_1.relay_id,
                ],
            }
        },
    )
    content = response.json()
    room_id = content["data"]["chatRoomCreate"]["room"]["node"]["id"]
    assert content["data"]["chatRoomCreate"]["room"]["node"]["participantsCount"] == 2

    response = graphql_user_client(
        UPDATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "roomId": room_id,
                "addParticipants": [friend_2.relay_id, friend_3.relay_id],
            }
        },
    )
    content = response.json()
    assert content["data"]["chatRoomUpdate"]["room"]["node"]["title"] == "group"
    assert content["data"]["chatRoomUpdate"]["room"]["node"]["participantsCount"] == 4

    participants = content["data"]["chatRoomUpdate"]["room"]["node"]["participants"]["edges"]
    assert len(participants) == 4
    ids = [participant["node"]["profile"]["id"] for participant in participants]
    assert friend_1.relay_id in ids
    assert friend_2.relay_id in ids
    assert friend_3.relay_id in ids


def test_admin_user_cant_add_repeated_or_existing_participants(
    django_user_client, graphql_user_client
):
    # already existing participants and repeated participants should be ignored
    friend_1 = ProfileFactory()
    friend_2 = ProfileFactory()
    friend_3 = ProfileFactory()

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "isGroup": True,
                "title": "group",
                "participants": [
                    friend_1.relay_id,
                ],
            }
        },
    )
    content = response.json()
    room_id = content["data"]["chatRoomCreate"]["room"]["node"]["id"]
    assert content["data"]["chatRoomCreate"]["room"]["node"]["participantsCount"] == 2

    response = graphql_user_client(
        UPDATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "roomId": room_id,
                "addParticipants": [
                    friend_1.relay_id,
                    friend_2.relay_id,
                    friend_3.relay_id,
                    friend_3.relay_id,
                ],
            }
        },
    )
    content = response.json()
    assert content["data"]["chatRoomUpdate"]["room"]["node"]["title"] == "group"
    assert content["data"]["chatRoomUpdate"]["room"]["node"]["participantsCount"] == 4

    participants = content["data"]["chatRoomUpdate"]["room"]["node"]["participants"]["edges"]
    assert len(participants) == 4
    ids = [participant["node"]["profile"]["id"] for participant in participants]
    assert django_user_client.user.profile.relay_id in ids
    assert friend_1.relay_id in ids
    assert friend_2.relay_id in ids
    assert friend_3.relay_id in ids
    assert ids.count(django_user_client.user.profile.relay_id) == 1
    assert ids.count(friend_1.relay_id) == 1
    assert ids.count(friend_2.relay_id) == 1
    assert ids.count(friend_3.relay_id) == 1


def test_admin_user_cant_add_invalid_participants(django_user_client, graphql_user_client):
    friend_1 = ProfileFactory()
    friend_2 = ProfileFactory()

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "isGroup": True,
                "title": "group",
                "participants": [
                    friend_1.relay_id,
                ],
            }
        },
    )
    content = response.json()
    room_id = content["data"]["chatRoomCreate"]["room"]["node"]["id"]
    assert content["data"]["chatRoomCreate"]["room"]["node"]["participantsCount"] == 2

    response = graphql_user_client(
        UPDATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "roomId": room_id,
                "addParticipants": ["123", friend_2.relay_id],
            }
        },
    )
    content = response.json()
    assert (
        content["data"]["chatRoomUpdate"]["errors"][0]["messages"][0]
        == "Some participants are not valid"
    )


def test_member_user_cant_add_participants(django_user_client, graphql_user_client, django_client):
    friend_1 = ProfileFactory()
    friend_2 = ProfileFactory()

    response = graphql_user_client(
        CREATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": django_user_client.user.profile.relay_id,
                "isGroup": True,
                "title": "group",
                "participants": [
                    friend_1.relay_id,
                ],
            }
        },
    )

    content = response.json()
    room_id = content["data"]["chatRoomCreate"]["room"]["node"]["id"]
    django_client.force_login(friend_1.owner)

    response = graphql_query(
        UPDATE_ROOM_GRAPHQL,
        variables={
            "input": {
                "profileId": friend_1.relay_id,
                "roomId": room_id,
                "addParticipants": [friend_2.relay_id],
            }
        },
        client=django_client,
    )
    content = response.json()
    assert (
        content["data"]["chatRoomUpdate"]["errors"][0]["messages"][0]
        == "You don't have permission to update this room"
    )
