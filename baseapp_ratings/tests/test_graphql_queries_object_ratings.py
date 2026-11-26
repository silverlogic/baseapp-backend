from django.test import override_settings

"""
Query-count tests for the `RatingsInterface`.

Mirrors `baseapp_reports/tests/test_graphql_queries_object_reports.py`: assert the
GraphQL `RatingsInterface` resolves in a flat number of database queries regardless
of how many `Rate` rows exist for the target — locks in the
`RatableMetadataService.annotate_queryset` optimisation and catches
`Coalesce`-mixing regressions.
"""

import pytest
from django.http import HttpResponse

from baseapp_core.testing import assert_max_queries, assert_queries_dont_grow
from baseapp_core.tests.factories import UserFactory

from .factories import RateFactory

pytestmark = pytest.mark.django_db


# Baseline for `ratingsCount` + `ratingsSum` + `ratingsAverage` on one User node:
# 1× relay `node()` (documentid + content_type JOIN) + 1× `users_user` load with
# `RatableMetadata` inlined as a Subquery via `pre_optimization_hook`.
# The User ContentType lookup counts too: `assert_max_queries` starts from a cold
# ContentType cache, so the number doesn't depend on which tests ran first.
# Update this number deliberately if you change the resolver / annotation path.
EXPECTED_RATINGS_INTERFACE_QUERY_COUNT = 3


COUNTS_ONLY_QUERY = """
    query GetUser($id: ID!) {
        node(id: $id) {
            ... on RatingsInterface {
                ratingsCount
                ratingsSum
                ratingsAverage
            }
        }
    }
"""


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_ratings_count_is_flat_regardless_of_rate_volume(graphql_client) -> None:
    """`ratingsCount` resolves off an annotation on the target fetch: 20 rates take the same
    queries as 3."""
    target = UserFactory()

    relay_id = target.relay_id  # resolve outside the capture

    def query() -> HttpResponse:
        return graphql_client(COUNTS_ONLY_QUERY, variables={"id": relay_id})

    assert_queries_dont_grow(
        run=query,
        add_items=lambda n: [
            RateFactory(target=target, user=UserFactory(), value=4) for _ in range(n)
        ],
        small=3,
        big=20,
        hint="RatableMetadataService.annotate_queryset is no longer applied to the target",
    )

    # Absolute baseline, catches regressions that bump both sides together.
    with assert_max_queries(EXPECTED_RATINGS_INTERFACE_QUERY_COUNT):
        response = query()
    assert response.json()["data"]["node"]["ratingsCount"] == 20


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_ratings_count_zero_when_no_rates_does_not_extra_query(graphql_client) -> None:
    """A target with no rates resolves in the same budget as one with rates: the metadata row
    doesn't exist yet, and `Coalesce` returns the zero defaults without an extra round trip."""
    target = UserFactory()

    relay_id = target.relay_id  # resolve outside the capture

    def query() -> HttpResponse:
        return graphql_client(COUNTS_ONLY_QUERY, variables={"id": relay_id})

    with assert_max_queries(EXPECTED_RATINGS_INTERFACE_QUERY_COUNT):
        response = query()
    assert response.json()["data"]["node"]["ratingsCount"] == 0

    assert_queries_dont_grow(
        run=query,
        add_items=lambda n: [
            RateFactory(target=target, user=UserFactory(), value=4) for _ in range(n)
        ],
        small=0,
        big=3,
        hint="a missing RatableMetadata row costs an extra query instead of falling to Coalesce",
    )
