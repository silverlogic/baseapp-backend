"""End-to-end tests for `mentioned_profile_ids` on chat send/edit message mutations.

Mentions live in `baseapp_mentions.Mention` — the chat Message model no longer
carries a `mentioned_profiles` M2M. The GraphQL `mentions` connection on
`MessageObjectType` is provided by `MentionsInterface` and returns `Mention`
nodes that expose the related `profile`.

The chat mutations follow the same contract as comments:

- `ChatRoomSendMessage` persists mentions when `mentionedProfileIds` is provided
  and silently no-ops when omitted.
- `ChatRoomEditMessage` replaces the mentions when `mentionedProfileIds` is
  given (including `[]` to clear) and preserves the existing mentions when the
  field is omitted.
- The sender (the profile passed via `profileId`) is excluded.
"""

import pytest
import swapper

from baseapp_mentions.tests.helpers import (
    mention_count,
    mentioned_profile_ids,
    seed_mentions,
)
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
                    mentions(first: 10) {
                        edges {
                            node {
                                id
                                profile {
                                    id
                                }
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
                    mentions(first: 10) {
                        edges {
                            node {
                                id
                                profile {
                                    id
                                }
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


def _set_up_two_person_room(user, friend) -> "ChatRoom":
    room = ChatRoomFactory(created_by=user)
    ChatRoomParticipantFactory(profile=user.profile, room=room)
    ChatRoomParticipantFactory(profile=friend, room=room)
    return room


@pytest.mark.celery_app
def test_send_message_persists_mentioned_profiles(
    django_user_client, graphql_user_client, celery_config
) -> None:
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
    assert mentioned_profile_ids(message) == {a.pk, b.pk}

    payload = content["data"]["chatRoomSendMessage"]["message"]["node"]
    assert {edge["node"]["profile"]["id"] for edge in payload["mentions"]["edges"]} == {
        a.relay_id,
        b.relay_id,
    }


@pytest.mark.celery_app
def test_send_message_without_mention_field_persists_no_mentions(
    django_user_client, graphql_user_client, celery_config
) -> None:
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
    assert mention_count(message) == 0


@pytest.mark.celery_app
def test_send_message_excludes_self_mention(
    django_user_client, graphql_user_client, celery_config
) -> None:
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
    assert mentioned_profile_ids(message) == {friend.pk}


def test_edit_message_replaces_mentioned_profiles(django_user_client, graphql_user_client) -> None:
    user = django_user_client.user
    friend = ProfileFactory()
    room = _set_up_two_person_room(user, friend)
    message = MessageFactory(room=room, profile=user.profile, user=user)
    a = ProfileFactory()
    b = ProfileFactory()
    c = ProfileFactory()
    seed_mentions(message, [a, b])

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
    assert mentioned_profile_ids(message) == {c.pk}


def test_edit_message_with_empty_list_clears_mentions(
    django_user_client, graphql_user_client
) -> None:
    user = django_user_client.user
    friend = ProfileFactory()
    room = _set_up_two_person_room(user, friend)
    message = MessageFactory(room=room, profile=user.profile, user=user)
    seed_mentions(message, [ProfileFactory(), ProfileFactory()])

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
    assert mention_count(message) == 0


def test_edit_message_without_mention_field_preserves_existing(
    django_user_client, graphql_user_client
) -> None:
    user = django_user_client.user
    friend = ProfileFactory()
    room = _set_up_two_person_room(user, friend)
    message = MessageFactory(room=room, profile=user.profile, user=user)
    a = ProfileFactory()
    seed_mentions(message, [a])

    response = graphql_user_client(
        EDIT_MESSAGE_WITH_MENTIONS_GRAPHQL,
        variables={
            "input": {
                "id": message.relay_id,
                "content": "edited body only",
            }
        },
    )

    # Pin success — the assertion below would also pass if the mutation
    # silently errored without touching mentions.
    payload = response.json()
    assert "errors" not in payload
    assert payload["data"]["chatRoomEditMessage"]["errors"] in (None, [])

    message.refresh_from_db()
    assert message.content == "edited body only"
    assert mentioned_profile_ids(message) == {a.pk}
