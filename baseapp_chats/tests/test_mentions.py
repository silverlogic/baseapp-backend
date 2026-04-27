"""End-to-end tests for `mentioned_profile_ids` on chat send/edit message mutations.

The chat mutations follow the same contract as comments:

- `ChatRoomSendMessage` persists the M2M when `mentionedProfileIds` is provided
  and silently no-ops when omitted.
- `ChatRoomEditMessage` replaces the M2M when `mentionedProfileIds` is given
  (including `[]` to clear) and preserves the existing mentions when the field
  is omitted.
- The sender (the profile passed via `profileId`) is excluded from the M2M.
- The `mentionedProfiles` field on `MessageObjectType` returns the persisted
  mentions.
"""

import pytest
import swapper

from baseapp_profiles.tests.factories import ProfileFactory

from .factories import ChatRoomFactory, ChatRoomParticipantFactory, MessageFactory

pytestmark = pytest.mark.django_db

ChatRoom = swapper.load_model("baseapp_chats", "ChatRoom")
Message = swapper.load_model("baseapp_chats", "Message")


SEND_MESSAGE_WITH_MENTIONS_GRAPHQL = """
    mutation SendMessageWithMentions($input: ChatRoomSendMessageInput!) {
        chatRoomSendMessage(input: $input) {
            message {
                node {
                    id
                    content
                    mentionedProfiles(first: 10) {
                        edges {
                            node {
                                id
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

EDIT_MESSAGE_WITH_MENTIONS_GRAPHQL = """
    mutation EditMessageWithMentions($input: ChatRoomEditMessageInput!) {
        chatRoomEditMessage(input: $input) {
            message {
                node {
                    id
                    content
                    mentionedProfiles(first: 10) {
                        edges {
                            node {
                                id
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


def _set_up_two_person_room(user, friend):
    room = ChatRoomFactory(created_by=user)
    ChatRoomParticipantFactory(profile=user.profile, room=room)
    ChatRoomParticipantFactory(profile=friend, room=room)
    return room


@pytest.mark.celery_app
def test_send_message_persists_mentioned_profiles(
    django_user_client, graphql_user_client, celery_config
):
    user = django_user_client.user
    friend = ProfileFactory()
    room = _set_up_two_person_room(user, friend)
    a = ProfileFactory()
    b = ProfileFactory()

    response = graphql_user_client(
        SEND_MESSAGE_WITH_MENTIONS_GRAPHQL,
        variables={
            "input": {
                "roomId": room.relay_id,
                "profileId": user.profile.relay_id,
                "content": "hi @a @b",
                "mentionedProfileIds": [a.relay_id, b.relay_id],
            }
        },
    )

    content = response.json()
    assert "errors" not in content
    message = Message.objects.filter(room=room).get()
    assert {p.pk for p in message.mentioned_profiles.all()} == {a.pk, b.pk}

    payload = content["data"]["chatRoomSendMessage"]["message"]["node"]
    assert {edge["node"]["id"] for edge in payload["mentionedProfiles"]["edges"]} == {
        a.relay_id,
        b.relay_id,
    }


@pytest.mark.celery_app
def test_send_message_without_mention_field_persists_no_mentions(
    django_user_client, graphql_user_client, celery_config
):
    user = django_user_client.user
    friend = ProfileFactory()
    room = _set_up_two_person_room(user, friend)

    graphql_user_client(
        SEND_MESSAGE_WITH_MENTIONS_GRAPHQL,
        variables={
            "input": {
                "roomId": room.relay_id,
                "profileId": user.profile.relay_id,
                "content": "no mentions",
            }
        },
    )

    message = Message.objects.filter(room=room).get()
    assert message.mentioned_profiles.count() == 0


@pytest.mark.celery_app
def test_send_message_excludes_self_mention(django_user_client, graphql_user_client, celery_config):
    user = django_user_client.user
    friend = ProfileFactory()
    room = _set_up_two_person_room(user, friend)

    graphql_user_client(
        SEND_MESSAGE_WITH_MENTIONS_GRAPHQL,
        variables={
            "input": {
                "roomId": room.relay_id,
                "profileId": user.profile.relay_id,
                "content": "@me @friend",
                "mentionedProfileIds": [user.profile.relay_id, friend.relay_id],
            }
        },
    )

    message = Message.objects.filter(room=room).get()
    assert list(message.mentioned_profiles.values_list("pk", flat=True)) == [friend.pk]


def test_edit_message_replaces_mentioned_profiles(django_user_client, graphql_user_client):
    user = django_user_client.user
    friend = ProfileFactory()
    room = _set_up_two_person_room(user, friend)
    message = MessageFactory(room=room, profile=user.profile, user=user)
    a = ProfileFactory()
    b = ProfileFactory()
    c = ProfileFactory()
    message.mentioned_profiles.set([a, b])

    graphql_user_client(
        EDIT_MESSAGE_WITH_MENTIONS_GRAPHQL,
        variables={
            "input": {
                "id": message.relay_id,
                "content": "edited",
                "mentionedProfileIds": [c.relay_id],
            }
        },
    )

    message.refresh_from_db()
    assert list(message.mentioned_profiles.values_list("pk", flat=True)) == [c.pk]


def test_edit_message_with_empty_list_clears_mentions(django_user_client, graphql_user_client):
    user = django_user_client.user
    friend = ProfileFactory()
    room = _set_up_two_person_room(user, friend)
    message = MessageFactory(room=room, profile=user.profile, user=user)
    message.mentioned_profiles.set([ProfileFactory(), ProfileFactory()])

    graphql_user_client(
        EDIT_MESSAGE_WITH_MENTIONS_GRAPHQL,
        variables={
            "input": {
                "id": message.relay_id,
                "content": "edited",
                "mentionedProfileIds": [],
            }
        },
    )

    message.refresh_from_db()
    assert message.mentioned_profiles.count() == 0


def test_edit_message_without_mention_field_preserves_existing(
    django_user_client, graphql_user_client
):
    user = django_user_client.user
    friend = ProfileFactory()
    room = _set_up_two_person_room(user, friend)
    message = MessageFactory(room=room, profile=user.profile, user=user)
    a = ProfileFactory()
    message.mentioned_profiles.set([a])

    graphql_user_client(
        EDIT_MESSAGE_WITH_MENTIONS_GRAPHQL,
        variables={
            "input": {
                "id": message.relay_id,
                "content": "edited body only",
            }
        },
    )

    message.refresh_from_db()
    assert list(message.mentioned_profiles.values_list("pk", flat=True)) == [a.pk]
