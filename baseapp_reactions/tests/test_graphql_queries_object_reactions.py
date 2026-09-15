"""
Query-count tests for the `ReactionsInterface`.

Mirrors `baseapp_ratings/tests/test_graphql_queries_object_ratings.py`: assert the
GraphQL `ReactionsInterface` resolves in a flat number of database queries
regardless of how many `Reaction` rows exist for the target — locks in the
`ReactableMetadataService.annotate_queryset` optimisation and catches
`Coalesce`-mixing regressions.
"""

import pytest
from constance.test import override_config
from django.contrib.contenttypes.models import ContentType

from baseapp_comments.tests.factories import CommentFactory
from baseapp_core.tests.factories import UserFactory

from .factories import ReactionFactory

pytestmark = pytest.mark.django_db


# Baseline for `reactionsCount` + `isReactionsEnabled` on one Comment node: 1× relay
# `node()` (documentid + content_type JOIN) + 1× `comments_comment` load with
# `ReactableMetadata` inlined as a Subquery via `pre_optimization_hook`.
# Update this number deliberately if you change the resolver / annotation path.
EXPECTED_REACTIONS_INTERFACE_QUERY_COUNT = 2


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


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_reactions_count_is_flat_regardless_of_reaction_volume(
    graphql_client_with_queries,
) -> None:
    """`reactionsCount` should be a flat query path: regardless of how many
    `Reaction` rows point at the target, the GraphQL query should make the same
    number of DB round-trips (modulo content-type cache jitter)."""
    target_small = CommentFactory()
    for _ in range(3):
        ReactionFactory(target=target_small, user=UserFactory())

    ContentType.objects.clear_cache()
    response_small, queries_small = graphql_client_with_queries(
        COUNTS_ONLY_QUERY, variables={"id": target_small.relay_id}
    )
    assert response_small.json()["data"]["node"]["reactionsCount"]["total"] == 3
    small_count = queries_small.count

    big_target = CommentFactory()
    for _ in range(20):
        ReactionFactory(target=big_target, user=UserFactory())

    ContentType.objects.clear_cache()
    response_big, queries_big = graphql_client_with_queries(
        COUNTS_ONLY_QUERY, variables={"id": big_target.relay_id}
    )
    assert response_big.json()["data"]["node"]["reactionsCount"]["total"] == 20

    assert queries_big.count == small_count
    # Absolute baseline, catches regressions that bump both sides together.
    assert small_count == EXPECTED_REACTIONS_INTERFACE_QUERY_COUNT


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_reactions_count_zero_when_no_reactions_does_not_extra_query(
    graphql_client_with_queries,
) -> None:
    """A target with no reactions should resolve in the same query budget as one
    with reactions — the metadata row simply doesn't exist yet, and `Coalesce`
    returns the zero defaults without an extra round trip."""
    target_with_reactions = CommentFactory()
    for _ in range(3):
        ReactionFactory(target=target_with_reactions, user=UserFactory())

    ContentType.objects.clear_cache()
    response_with, queries_with = graphql_client_with_queries(
        COUNTS_ONLY_QUERY, variables={"id": target_with_reactions.relay_id}
    )
    assert response_with.json()["data"]["node"]["reactionsCount"]["total"] == 3

    target_empty = CommentFactory()

    ContentType.objects.clear_cache()
    response_empty, queries_empty = graphql_client_with_queries(
        COUNTS_ONLY_QUERY, variables={"id": target_empty.relay_id}
    )
    assert response_empty.json()["data"]["node"]["reactionsCount"]["total"] == 0

    assert queries_empty.count == queries_with.count
    # Absolute baseline, same expected count as the populated path.
    assert queries_empty.count == EXPECTED_REACTIONS_INTERFACE_QUERY_COUNT
