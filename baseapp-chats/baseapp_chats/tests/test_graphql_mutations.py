import pytest
import swapper
from baseapp_blocks.tests.factories import BlockFactory
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory
from django.test.client import MULTIPART_CONTENT

from .factories import ChatRoomFactory, ChatRoomParticipantFactory, MessageFactory
from .test_graphql_queries import PROFILE_ROOMS_GRAPHQL

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
    response = graphql_user_client(
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
