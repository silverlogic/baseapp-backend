"""Query-count regression tests for chats GraphQL resolvers.

These tests pin the cost of the paths the plugin refactor touched. They
exist to trip when a future change loses a prefetch or drops an
optimizer hook — the bounds are tight enough to catch a fan-out
regression but loose enough to absorb optimizer-internal churn.

Modelled after:
- baseapp_mentions/tests/test_graphql.py (`CaptureQueriesContext` +
  asserted upper bound; "Likely cause:" hints in assertion messages).
- baseapp_follows/tests/test_follow_count.py (SQL-shape assertions when
  the count alone is too coarse).
"""

from typing import TYPE_CHECKING

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

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
    """Regression guard: paged `chatRooms` listing stays flat regardless
    of room count, with `lastMessage` batched (not per-row).

    Baseline for (5 rooms, 3 extra participants each, 1 message each)
    is 11 queries — request setup (4) + permission check (1) +
    ContentType lookups (2, cold-start only) + COUNT (1) + page (1)
    + batched `lastMessage` (1) + COMMIT (1).

    A per-room `lastMessage` regression would push the count to
    ~16+ (5 extra round-trips), so the bound below trips immediately.
    """
    my_profile = django_user_client.user.profile
    _set_up_rooms_with_participants(my_profile, n_rooms=5, n_other_participants_per_room=3)

    with CaptureQueriesContext(connection) as ctx:
        response = graphql_user_client(USER_CHAT_ROOMS_LISTING)

    assert "errors" not in response.json(), response.json()
    # ~11 queries today. 15 absorbs minor optimiser shifts (e.g. an
    # extra ContentType cache miss); any per-room fan-out blows past it.
    assert len(ctx.captured_queries) <= 15, (
        f"Chat room listing issued {len(ctx.captured_queries)} queries. "
        "Likely causes (priority order):\n"
        "  - `last_message` lost its batched prefetch (now per-row)\n"
        "  - `chat_rooms` reverted to `DjangoFilterConnectionField`\n"
        "  - `ChatRoomsInterface.resolve_chat_rooms` block-exclusion "
        "subqueries became per-row"
    )


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
    messages = [MessageFactory(room=room, profile=my_profile) for _ in range(5)]
    for message in messages:
        seed_mentions(message, mention_targets)

    with CaptureQueriesContext(connection) as ctx:
        response = graphql_user_client(
            ROOM_MESSAGES_WITH_MENTIONS, variables={"roomId": room.relay_id}
        )

    assert "errors" not in response.json(), response.json()
    # ~17 queries today, comparable to the comments+mentions baseline.
    # 20 absorbs minor optimiser-internals shifts; trips immediately
    # on any of the three regressions named in the docstring.
    assert len(ctx.captured_queries) <= 20, (
        f"Messages-with-mentions listing issued {len(ctx.captured_queries)} queries. "
        "Likely causes (in priority order):\n"
        "  - `chatRoom.allMessages` reverted to `DjangoFilterConnectionField`\n"
        "  - `BaseMessageObjectType.pre_optimization_hook` dropped one of "
        "`room_id` / `deleted` / `message_type` from `only_fields`\n"
        "  - `MentionsInterface.mentions.optimizer_hook` was lost\n"
        "  - Message ObjectType lost its `document = GenericRelation(DocumentId)`"
    )


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
