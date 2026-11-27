"""
Query-count tests for the MentionsInterface.

Mirrors `baseapp_follows/tests/test_graphql_queries_object_follows.py`:
exercises the GraphQL `MentionsInterface` against a paginated parent
(`Comment`) and asserts that the number of database queries does NOT scale
with the number of mention rows. Locks in the optimizer + annotation path
(`MentionableMetadataService.annotate_queryset`) and catches regressions
where a resolver reverts to a per-row `DocumentId.get_or_create_for_object`
or per-row `count()`.

`mentionsCount` and `mentions` are fully batchable (a subquery annotation and an
optimizer prefetch). `isMentioningProfile` still costs a fixed number of queries per
child; its test declares that bound instead of pretending it's flat.
"""

from typing import TYPE_CHECKING

import pytest
from django.http import HttpResponse

from baseapp_comments.tests.factories import CommentFactory
from baseapp_core.testing import assert_queries_dont_grow
from baseapp_mentions.tests.helpers import seed_mentions
from baseapp_profiles.tests.factories import ProfileFactory

if TYPE_CHECKING:
    from baseapp_comments.models import Comment

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


def _make_mentioned_comments(parent, n_children, profiles) -> "list[Comment]":
    """Create `n_children` reply Comments under `parent`, each mentioning `profiles`."""
    children = [CommentFactory(in_reply_to=parent) for _ in range(n_children)]
    for child in children:
        seed_mentions(child, profiles)
    return children


def test_mentions_count_is_flat_across_paginated_parents(graphql_user_client) -> None:
    """`mentionsCount` resolves off the `_mentions_count` subquery annotation added by
    `MentionableMetadataService.annotate_queryset` in
    `BaseCommentObjectType.pre_optimization_hook`. The query count must NOT grow with the
    number of child comments."""
    profiles = [ProfileFactory() for _ in range(3)]
    parent = CommentFactory()
    relay_id = parent.relay_id  # resolve outside the capture

    def query() -> HttpResponse:
        return graphql_user_client(COUNTS_ONLY_QUERY, variables={"targetId": relay_id})

    assert_queries_dont_grow(
        run=query,
        add_items=lambda n: _make_mentioned_comments(parent, n, profiles),
        small=3,
        big=10,
        hint="mentionsCount is no longer annotated on the comment list",
    )

    edges = query().json()["data"]["node"]["comments"]["edges"]
    assert len(edges) == 10
    assert all(e["node"]["mentionsCount"] == 3 for e in edges)


def test_is_mentioning_profile_is_flat_across_paginated_parents(graphql_user_client) -> None:
    """`isMentioningProfile` reads off `_mention_target_doc_id`, so the existence check is one
    indexed lookup per child with no extra DocumentId lookup. Each extra child still costs 3
    queries today (the `Mention.exists()` and the per-node GraphQL permission walk); the test
    declares that linear cost so it can't get worse unnoticed."""
    profiles = [ProfileFactory() for _ in range(2)]
    needle = profiles[0]
    parent = CommentFactory()
    variables = {"targetId": parent.relay_id, "profileId": needle.relay_id}

    def query() -> HttpResponse:
        return graphql_user_client(IS_MENTIONING_QUERY, variables=variables)

    assert_queries_dont_grow(
        run=query,
        add_items=lambda n: _make_mentioned_comments(parent, n, profiles),
        small=3,
        big=8,
        # Accepted: measured at 3 per child. A DocumentId fetch back in the resolver makes it 4.
        per_item=3,
        hint="a DocumentId fetch is back in resolve_is_mentioning_profile",
    )

    edges = query().json()["data"]["node"]["comments"]["edges"]
    assert all(e["node"]["isMentioningProfile"] is True for e in edges)


def test_mentions_connection_stays_flat_across_paginated_parents(graphql_user_client) -> None:
    """`mentions` is wired into the optimizer via `MentionsInterface.mentions.optimizer_hook`,
    which promotes the field to a real `prefetch_related('document__<reverse>')` chain on the
    consumer's queryset. The whole mention set loads in one batched SELECT per page of
    consumers (plus one batched SELECT for the referenced Profiles), so the cost does NOT
    scale with the number of children.

    If a regression drops the optimizer hook (or the consumer model loses its
    `document = GenericRelation(DocumentId)`), the resolver falls back to per-parent fan-out
    and this test trips.
    """
    profiles = [ProfileFactory() for _ in range(3)]
    parent = CommentFactory()
    relay_id = parent.relay_id

    assert_queries_dont_grow(
        run=lambda: graphql_user_client(MENTIONS_QUERY, variables={"targetId": relay_id}),
        add_items=lambda n: _make_mentioned_comments(parent, n, profiles),
        small=3,
        big=8,
        hint=(
            "MentionsInterface.mentions.optimizer_hook was lost, or Comment no longer has "
            "`document = GenericRelation(DocumentId)`"
        ),
    )
