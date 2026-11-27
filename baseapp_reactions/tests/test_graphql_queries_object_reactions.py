from django.test import override_settings

"""
Query-count tests for the `ReactionsInterface`.

Mirrors `baseapp_ratings/tests/test_graphql_queries_object_ratings.py`: assert the
GraphQL `ReactionsInterface` resolves in a flat number of database queries
regardless of how many `Reaction` rows exist for the target — locks in the
`ReactableMetadataService.annotate_queryset` optimisation and catches
`Coalesce`-mixing regressions.
"""

import pytest
from django.http import HttpResponse

from baseapp_comments.tests.factories import CommentFactory
from baseapp_core.testing import assert_max_queries, assert_queries_dont_grow
from baseapp_core.tests.factories import UserFactory

from .factories import ReactionFactory

pytestmark = pytest.mark.django_db


# Baseline for `reactionsCount` + `isReactionsEnabled` on one Comment node: 1× relay
# `node()` (documentid + content_type JOIN) + 1× `comments_comment` load with
# `ReactableMetadata` inlined as a Subquery via `pre_optimization_hook`.
# The Comment ContentType lookup counts too: `assert_max_queries` starts from a cold
# ContentType cache, so the number doesn't depend on which tests ran first.
# Update this number deliberately if you change the resolver / annotation path.
EXPECTED_REACTIONS_INTERFACE_QUERY_COUNT = 3


COUNTS_ONLY_QUERY = """
    query GetTarget($id: ID!) {
        node(id: $id) {
            ... on ReactionsInterface {
                reactionsCount {
                    total
                    LIKE
                    DISLIKE
                }
                isReactionsEnabled
            }
        }
    }
"""


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_reactions_count_is_flat_regardless_of_reaction_volume(graphql_client) -> None:
    """`reactionsCount` resolves off an annotation on the target fetch: 20 reactions take the
    same queries as 3."""
    target = CommentFactory()

    relay_id = target.relay_id  # resolve outside the capture

    def query() -> HttpResponse:
        return graphql_client(COUNTS_ONLY_QUERY, variables={"id": relay_id})

    assert_queries_dont_grow(
        run=query,
        add_items=lambda n: [ReactionFactory(target=target, user=UserFactory()) for _ in range(n)],
        small=3,
        big=20,
        hint="ReactableMetadataService.annotate_queryset is no longer applied to the target",
    )

    # Absolute baseline, catches regressions that bump both sides together.
    with assert_max_queries(EXPECTED_REACTIONS_INTERFACE_QUERY_COUNT):
        response = query()
    assert response.json()["data"]["node"]["reactionsCount"]["total"] == 20


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_reactions_count_zero_when_no_reactions_does_not_extra_query(graphql_client) -> None:
    """A target with no reactions resolves in the same budget as one with reactions: the
    metadata row doesn't exist yet, and `Coalesce` returns the zero defaults without an extra
    round trip."""
    target = CommentFactory()

    relay_id = target.relay_id  # resolve outside the capture

    def query() -> HttpResponse:
        return graphql_client(COUNTS_ONLY_QUERY, variables={"id": relay_id})

    with assert_max_queries(EXPECTED_REACTIONS_INTERFACE_QUERY_COUNT):
        response = query()
    assert response.json()["data"]["node"]["reactionsCount"]["total"] == 0

    assert_queries_dont_grow(
        run=query,
        add_items=lambda n: [ReactionFactory(target=target, user=UserFactory()) for _ in range(n)],
        small=0,
        big=3,
        hint="a missing ReactableMetadata row costs an extra query instead of falling to Coalesce",
    )
