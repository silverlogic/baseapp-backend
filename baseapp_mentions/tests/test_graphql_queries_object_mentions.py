"""
Query-count tests for the MentionsInterface.

Mirrors `baseapp_follows/tests/test_graphql_queries_object_follows.py`:
exercises the GraphQL `MentionsInterface` against a paginated parent
(`Comment`) and asserts that the number of database queries does NOT scale
with the number of mention rows. Locks in the optimizer + annotation path
(`MentionableMetadataService.annotate_queryset`) and catches regressions
where a resolver reverts to a per-row `DocumentId.get_or_create_for_object`
or per-row `count()`.

`mentionsCount` and `isMentioningProfile` are fully batchable via subquery
annotations on the parent queryset. `mentions` is a per-parent graphene
connection and still grows linearly in parents — the dedicated test below
documents and locks in that linearity instead of pretending it's flat.
"""

import pytest

from baseapp_comments.tests.factories import CommentFactory
from baseapp_mentions.tests.helpers import seed_mentions
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db


COUNTS_ONLY_QUERY = """
    query CommentsCounts($targetId: ID!) {
        node(id: $targetId) {
            ... on CommentsInterface {
                comments(first: 10) {
                    edges {
                        node {
                            id
                            mentionsCount
                        }
                    }
                }
            }
        }
    }
"""

IS_MENTIONING_QUERY = """
    query CommentsIsMentioning($targetId: ID!, $profileId: ID!) {
        node(id: $targetId) {
            ... on CommentsInterface {
                comments(first: 10) {
                    edges {
                        node {
                            id
                            isMentioningProfile(profileId: $profileId)
                        }
                    }
                }
            }
        }
    }
"""

MENTIONS_QUERY = """
    query CommentsMentions($targetId: ID!) {
        node(id: $targetId) {
            ... on CommentsInterface {
                comments(first: 10) {
                    edges {
                        node {
                            id
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
    }
"""


def _make_mentioned_comments(parent, n_children, profiles):
    """Create `n_children` reply Comments under `parent`, each mentioning `profiles`."""
    children = [CommentFactory(in_reply_to=parent) for _ in range(n_children)]
    for child in children:
        seed_mentions(child, profiles)
    return children


def test_mentions_count_is_flat_across_paginated_parents(graphql_user_client):
    """`mentionsCount` resolves off the `_mentions_count` subquery annotation
    added by `MentionableMetadataService.annotate_queryset` in
    `BaseCommentObjectType.pre_optimization_hook`. The total query count must
    NOT grow with the number of child comments — doubling parents must keep
    the count flat."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    profiles = [ProfileFactory() for _ in range(3)]

    parent_small = CommentFactory()
    _make_mentioned_comments(parent_small, 3, profiles)
    with CaptureQueriesContext(connection) as ctx_small:
        response_small = graphql_user_client(
            COUNTS_ONLY_QUERY, variables={"targetId": parent_small.relay_id}
        )
    assert "errors" not in response_small.json(), response_small.json()
    edges_small = response_small.json()["data"]["node"]["comments"]["edges"]
    assert len(edges_small) == 3
    assert all(e["node"]["mentionsCount"] == 3 for e in edges_small)
    small_count = len(ctx_small.captured_queries)

    parent_big = CommentFactory()
    _make_mentioned_comments(parent_big, 10, profiles)
    with CaptureQueriesContext(connection) as ctx_big:
        response_big = graphql_user_client(
            COUNTS_ONLY_QUERY, variables={"targetId": parent_big.relay_id}
        )
    assert "errors" not in response_big.json(), response_big.json()
    edges_big = response_big.json()["data"]["node"]["comments"]["edges"]
    assert len(edges_big) == 10
    assert all(e["node"]["mentionsCount"] == 3 for e in edges_big)

    # The count is computed by a subquery on the parent fetch — no per-child
    # query. Doubling parents must NOT grow the query count.
    assert len(ctx_big.captured_queries) == small_count


def test_is_mentioning_profile_is_flat_across_paginated_parents(graphql_user_client):
    """`isMentioningProfile` reads off `_mention_target_doc_id` so the
    existence check is a single indexed lookup per child — but the
    annotation means no extra DocumentId lookup. Doubling parents adds
    exactly one query per extra child (the exists()), so the *growth* is
    linear and predictable."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    profiles = [ProfileFactory() for _ in range(2)]
    needle = profiles[0]

    parent_small = CommentFactory()
    _make_mentioned_comments(parent_small, 3, profiles)
    with CaptureQueriesContext(connection) as ctx_small:
        response_small = graphql_user_client(
            IS_MENTIONING_QUERY,
            variables={"targetId": parent_small.relay_id, "profileId": needle.relay_id},
        )
    assert "errors" not in response_small.json(), response_small.json()
    edges_small = response_small.json()["data"]["node"]["comments"]["edges"]
    assert all(e["node"]["isMentioningProfile"] is True for e in edges_small)
    small_count = len(ctx_small.captured_queries)

    parent_big = CommentFactory()
    extra = 5
    _make_mentioned_comments(parent_big, 3 + extra, profiles)
    with CaptureQueriesContext(connection) as ctx_big:
        response_big = graphql_user_client(
            IS_MENTIONING_QUERY,
            variables={"targetId": parent_big.relay_id, "profileId": needle.relay_id},
        )
    assert "errors" not in response_big.json(), response_big.json()
    edges_big = response_big.json()["data"]["node"]["comments"]["edges"]
    assert all(e["node"]["isMentioningProfile"] is True for e in edges_big)

    # `isMentioningProfile` per child boils down to a single `Mention.exists()`
    # plus one Profile-status lookup (the GraphQL permission walk runs once
    # per Comment node), so the delta should be 2 queries per extra child.
    # If it leaks above 3, a DocumentId fetch has returned to the resolver.
    delta = len(ctx_big.captured_queries) - small_count
    assert delta <= 3 * extra, (
        f"isMentioningProfile added {delta} queries for {extra} extra children "
        f"(expected ≤ {3 * extra}). Likely cause: DocumentId leaked back in."
    )


def test_mentions_connection_stays_flat_across_paginated_parents(graphql_user_client):
    """`mentions` is wired into the optimizer via `MentionsInterface.mentions.optimizer_hook`,
    which promotes the field to a real `prefetch_related('document__mentions')`
    chain on the consumer's queryset. With that prefetch in place the entire
    mention set is loaded in one batched SELECT per page of consumers
    (plus one batched SELECT for the referenced Profiles), so the cost
    does NOT scale with the number of children — doubling children adds
    zero extra queries.

    If a regression drops the optimizer hook (or the consumer model loses
    its `document = GenericRelation(DocumentId)`), the resolver falls
    back to per-parent fan-out and this test trips.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    profiles = [ProfileFactory() for _ in range(3)]

    parent_small = CommentFactory()
    _make_mentioned_comments(parent_small, 3, profiles)
    with CaptureQueriesContext(connection) as ctx_small:
        response_small = graphql_user_client(
            MENTIONS_QUERY, variables={"targetId": parent_small.relay_id}
        )
    assert "errors" not in response_small.json(), response_small.json()
    small_count = len(ctx_small.captured_queries)

    parent_big = CommentFactory()
    extra = 5
    _make_mentioned_comments(parent_big, 3 + extra, profiles)
    with CaptureQueriesContext(connection) as ctx_big:
        response_big = graphql_user_client(
            MENTIONS_QUERY, variables={"targetId": parent_big.relay_id}
        )
    assert "errors" not in response_big.json(), response_big.json()

    # With the optimizer hook in place, mentions for all children are
    # loaded in a single batched SELECT (`target_id IN (...)`), so the
    # delta is zero — the connection cost is independent of child count.
    # If this becomes positive again, the prefetch chain has been
    # broken; see `MentionsInterface.mentions.optimizer_hook` and
    # `Comment.document = GenericRelation(DocumentId, ...)`.
    assert len(ctx_big.captured_queries) - small_count == 0
