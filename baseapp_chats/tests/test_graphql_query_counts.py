"""Query-count regression tests for chats GraphQL resolvers.

These tests pin the cost of the paths the plugin refactor touched. They
exist to trip when a future change loses a prefetch or drops an
optimizer hook — the bounds are tight enough to catch a fan-out
regression but loose enough to absorb optimizer-internal churn.

Counts use `assert_queries_dont_grow` / `assert_max_queries` from
`baseapp_core.testing`. Where the count alone is too coarse, a test
asserts on the SQL shape instead (as baseapp_follows/tests/test_follow_count.py
does).
"""

from typing import TYPE_CHECKING

import pytest
from django.db import connection
from django.http import HttpResponse
from django.test.utils import CaptureQueriesContext

from baseapp_core.testing import assert_max_queries, assert_queries_dont_grow
from baseapp_mentions.tests.helpers import seed_mentions
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import ChatRoomFactory, ChatRoomParticipantFactory, MessageFactory

if TYPE_CHECKING:
    from django.db.models import Model

pytestmark = pytest.mark.django_db


def _captured_sql(ctx) -> list[str]:
    return [q["sql"] for q in ctx.captured_queries]


USER_CHAT_ROOMS_LISTING = """
    query UserChatRooms {
        me {
            profile {
                chatRooms {
                    edges {
                        node {
                            id
                            lastMessage {
                                id
                                content
                            }
                        }
                    }
                }
            }
        }
    }
"""


PROFILE_UNREAD_COUNT = """
    query ProfileUnreadCount($profileId: ID!) {
        profile(id: $profileId) {
            id
            ... on ChatRoomsInterface {
                unreadMessagesCount
            }
        }
    }
"""


ROOM_MESSAGES_WITH_MENTIONS = """
    query RoomMessagesWithMentions($roomId: ID!) {
        chatRoom(id: $roomId) {
            allMessages {
                edges {
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
            }
        }
    }
"""


def _set_up_rooms_with_participants(
    my_profile, n_rooms, n_other_participants_per_room
) -> "list[Model]":
    """Create n rooms, place my_profile in each, add n_other participants
    + one message so each room is visible to my_profile."""
    rooms = []
    for _ in range(n_rooms):
        room = ChatRoomFactory(created_by=my_profile.owner, created_by_profile=my_profile)
        ChatRoomParticipantFactory(profile=my_profile, room=room)
        for _ in range(n_other_participants_per_room):
            other = ProfileFactory()
            ChatRoomParticipantFactory(profile=other, room=room)
            MessageFactory(room=room, profile=other)
        rooms.append(room)
    return rooms


def test_paginated_chat_rooms_does_not_explode_query_count(
    graphql_user_client, django_user_client
) -> None:
    """Regression guard: paged `chatRooms` listing stays flat regardless of room count, with
    `lastMessage` batched (not per-row). A per-room `lastMessage` adds a query per room."""
    my_profile = django_user_client.user.profile
    hint = (
        "`last_message` lost its batched prefetch (now per-row), `chat_rooms` reverted to "
        "`DjangoFilterConnectionField`, or the `ChatRoomsInterface.resolve_chat_rooms` "
        "block-exclusion subqueries became per-row"
    )

    def query() -> HttpResponse:
        return graphql_user_client(USER_CHAT_ROOMS_LISTING)

    assert_queries_dont_grow(
        run=query,
        add_items=lambda n: _set_up_rooms_with_participants(
            my_profile, n_rooms=n, n_other_participants_per_room=3
        ),
        small=1,
        big=5,
        hint=hint,
    )

    with assert_max_queries(9, hint=hint):
        query()


def test_chat_rooms_listing_unread_count_subquery_runs_once_per_page(
    graphql_user_client, django_user_client
) -> None:
    """SQL-shape guard for `unreadMessagesCount`.

    `ChatRoomsInterface.resolve_unread_messages_count` aggregates
    UnreadMessageCount with a single `Sum`. The single-profile
    `profile(id: ...)` query path should issue exactly one aggregate
    query touching `baseapp_chats_unreadmessagecount`, not one per row
    or one per participant.
    """
    my_profile = django_user_client.user.profile
    _set_up_rooms_with_participants(my_profile, n_rooms=4, n_other_participants_per_room=2)

    with CaptureQueriesContext(connection) as ctx:
        response = graphql_user_client(
            PROFILE_UNREAD_COUNT, variables={"profileId": my_profile.relay_id}
        )

    payload = response.json()
    assert "errors" not in payload, payload
    assert payload["data"]["profile"]["unreadMessagesCount"] is not None, (
        f"unreadMessagesCount returned None — the resolver was probably "
        f"denied by `baseapp_chats.list_chatrooms` permission check. "
        f"Full payload: {payload}"
    )

    sql = _captured_sql(ctx)
    # The concrete table name is whatever the consuming project chose
    # for its `UnreadMessageCount` swap target. In testproject that's
    # `chats_unreadmessagecount`; match on the model-suffix only so a
    # different app_label doesn't silently disarm this assertion.
    unread_aggregates = [
        q for q in sql if "_unreadmessagecount" in q.lower() and "sum(" in q.lower()
    ]
    assert len(unread_aggregates) == 1, (
        f"Expected exactly one SUM aggregate over UnreadMessageCount; got "
        f"{len(unread_aggregates)}. Likely cause: resolver_unread_messages_count "
        "started running per-room instead of as a single aggregate. "
        f"Captured SQL: {sql}"
    )


def test_mentions_interface_on_messages_rides_optimizer_prefetch(
    graphql_user_client, django_user_client
) -> None:
    """Regression guard: the `MentionsInterface` optimizer hook on
    `MessageObjectType` must batch the `document__<reverse>` mentions prefetch,
    and the chats-side `pre_optimization_hook` must keep `room_id`,
    `deleted`, and `message_type` in `only_fields`.

    Three things have to line up to keep the count flat:

    1. `chatRoom.allMessages` is `query_optimizer.DjangoConnectionField`
       (not `graphene_django.filter.DjangoFilterConnectionField`),
       so the optimizer compiler actually runs and fires the mentions
       hook.
    2. `MentionsInterface.mentions.optimizer_hook` is intact (walks
       `document__<reverse>` through the parent optimizer).
    3. `BaseMessageObjectType.pre_optimization_hook` adds `room_id`,
       `deleted`, and `message_type` to `only_fields` so neither the
       prefetch pipeline nor `resolve_content` triggers per-message
       `refresh_from_db`.

    Drop any of those and the count jumps: missing (1) → ~54;
    missing (3) → ~32 (5 prefetch-link refreshes + 10 deferred
    field loads); missing (2) → fan-out as `messages * mentions`.
    """
    my_profile = django_user_client.user.profile
    other = ProfileFactory()
    room = ChatRoomFactory(created_by=my_profile.owner, created_by_profile=my_profile)
    ChatRoomParticipantFactory(profile=my_profile, room=room)
    ChatRoomParticipantFactory(profile=other, room=room)

    mention_targets = [ProfileFactory() for _ in range(3)]
    room_id = room.relay_id  # resolve outside the capture
    hint = (
        "`chatRoom.allMessages` reverted to `DjangoFilterConnectionField`, "
        "`BaseMessageObjectType.pre_optimization_hook` dropped one of `room_id` / `deleted` / "
        "`message_type` from `only_fields`, `MentionsInterface.mentions.optimizer_hook` was "
        "lost, or the Message ObjectType lost its `document = GenericRelation(DocumentId)`"
    )

    def add_messages(n: int) -> None:
        for _ in range(n):
            seed_mentions(MessageFactory(room=room, profile=my_profile), mention_targets)

    def query() -> HttpResponse:
        return graphql_user_client(ROOM_MESSAGES_WITH_MENTIONS, variables={"roomId": room_id})

    assert_queries_dont_grow(run=query, add_items=add_messages, small=1, big=5, hint=hint)

    with assert_max_queries(16, hint=hint):
        query()


UNREAD_FILTERED_ROOMS = """
    query UnreadFilteredRooms($profileId: ID!) {
        profile(id: $profileId) {
            id
            ... on ChatRoomsInterface {
                chatRooms(unreadMessages: true) {
                    edges {
                        node {
                            id
                            unreadMessages(profileId: $profileId) {
                                count
                            }
                        }
                    }
                }
            }
        }
    }
"""


def test_chat_room_filter_unread_messages_prefetches_unread_messages(
    graphql_user_client, django_user_client
) -> None:
    """SQL-shape guard for `ChatRoomFilter.filter_unread_messages`.

    The filter calls `queryset.prefetch_related("unread_messages")` —
    that prefetch must be a single batched query, not one per room.
    """
    my_profile = django_user_client.user.profile
    other = ProfileFactory()
    for _ in range(4):
        room = ChatRoomFactory(created_by=my_profile.owner, created_by_profile=my_profile)
        ChatRoomParticipantFactory(profile=my_profile, room=room)
        ChatRoomParticipantFactory(profile=other, room=room)
        MessageFactory(room=room, profile=other)

    with CaptureQueriesContext(connection) as ctx:
        response = graphql_user_client(
            UNREAD_FILTERED_ROOMS, variables={"profileId": my_profile.relay_id}
        )

    assert "errors" not in response.json(), response.json()
    sql = _captured_sql(ctx)
    # The `unread_messages` prefetch should issue a single `IN (...)`
    # query batched across all paged rooms — not one per room. The
    # `unreadMessages(profileId:)` field-level resolver does add per-row
    # lookups, but the *prefetch* itself should be batched.
    prefetch_queries = [
        q for q in sql if "_unreadmessagecount" in q.lower() and 'room_id" in' in q.lower()
    ]
    assert len(prefetch_queries) <= 1, (
        f"`unread_messages` prefetch ran {len(prefetch_queries)} times; "
        "expected a single batched IN query. Likely cause: "
        "`ChatRoomFilter.filter_unread_messages` lost its prefetch_related "
        "call, or the queryset got re-evaluated mid-pagination. "
        f"Offending queries: {prefetch_queries}"
    )


MANAGEABLE_ROOMS_WITH_IS_PARTICIPANT_LISTING = """
    query ManageableRooms($profileId: ID!, $contactId: ID!) {
        profile(id: $profileId) {
            id
            ... on ChatRoomsInterface {
                chatRooms(manageable: true) {
                    edges {
                        node {
                            id
                            title
                            participantsCount
                            isParticipant(profileId: $contactId)
                        }
                    }
                }
            }
        }
    }
"""


def test_manageable_listing_with_is_participant_stays_linear(
    graphql_user_client, django_user_client
) -> None:
    """Bound guard for the add-contact-to-group listing.

    `isParticipant(profileId:)` resolves one indexed EXISTS per row —
    an accepted per-row cost bounded by page size (same precedent as
    `resolve_is_archived`). The relay-id decode of `profileId` is
    memoized per request, so it must NOT scale with row count.

    The test declares that per-room cost. Another per-row query (e.g. an
    un-memoized decode, or hydrating participant profiles like
    `participant_ids` does) trips it immediately.
    """
    import swapper

    from baseapp_profiles.tests.factories import ProfileFactory as _ProfileFactory

    ChatRoomParticipant = swapper.load_model("baseapp_chats", "ChatRoomParticipant")
    roles = ChatRoomParticipant.ChatRoomParticipantRoles

    my_profile = django_user_client.user.profile
    contact = _ProfileFactory()
    variables = {"profileId": my_profile.relay_id, "contactId": contact.relay_id}

    def add_rooms(n: int) -> None:
        for i in range(n):
            room = ChatRoomFactory(is_group=True, title=f"group {i}")
            ChatRoomParticipantFactory(room=room, profile=my_profile, role=roles.ADMIN)
            ChatRoomParticipantFactory(room=room, profile=_ProfileFactory(), role=roles.MEMBER)
            room.participants_count = 2
            room.save(update_fields=["participants_count"])

    assert_queries_dont_grow(
        run=lambda: graphql_user_client(
            MANAGEABLE_ROOMS_WITH_IS_PARTICIPANT_LISTING, variables=variables
        ),
        add_items=add_rooms,
        small=1,
        big=5,
        # Accepted for now, two per room: the indexed EXISTS for `isParticipant`, and a
        # deferred `is_group` load in `resolve_title` (the field is not in the optimizer's
        # `only_fields`). BE-5b removes the second one and lowers this to 1.
        per_item=2,
        hint=(
            "`resolve_is_participant` started hydrating profiles instead of EXISTS, the "
            "`manageable` filter join lost `.distinct()` and duplicated rows, or a per-row "
            "COUNT crept into `participants_count` resolution"
        ),
    )
