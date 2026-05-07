"""
Query-count tests for the `RatingsInterface`.

Mirrors `baseapp_reports/tests/test_graphql_queries_object_reports.py`: assert the
GraphQL `RatingsInterface` resolves in a flat number of database queries regardless
of how many `Rate` rows exist for the target — locks in the
`RatableMetadataService.annotate_queryset` optimisation and catches
`Coalesce`-mixing regressions.
"""

import pytest
from constance.test import override_config
from django.contrib.contenttypes.models import ContentType

from baseapp_core.tests.factories import UserFactory

from .factories import RateFactory

pytestmark = pytest.mark.django_db


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


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_ratings_count_is_flat_regardless_of_rate_volume(
    django_user_client, graphql_client_with_queries
):
    """`ratingsCount` should be a flat query path: regardless of how many `Rate`
    rows point at the target, the GraphQL query should make the same number of DB
    round-trips (modulo content-type cache jitter)."""
    target_small = django_user_client.user
    for _ in range(3):
        RateFactory(target=target_small, user=UserFactory(), value=4)

    ContentType.objects.clear_cache()
    response_small, queries_small = graphql_client_with_queries(
        COUNTS_ONLY_QUERY, variables={"id": target_small.relay_id}
    )
    assert response_small.json()["data"]["node"]["ratingsCount"] == 3
    small_count = queries_small.count

    big_target = UserFactory()
    for _ in range(20):
        RateFactory(target=big_target, user=UserFactory(), value=5)

    ContentType.objects.clear_cache()
    response_big, queries_big = graphql_client_with_queries(
        COUNTS_ONLY_QUERY, variables={"id": big_target.relay_id}
    )
    assert response_big.json()["data"]["node"]["ratingsCount"] == 20

    # 20 rates vs. 3 rates: query count must not grow with row count.
    assert queries_big.count == small_count


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_ratings_count_zero_when_no_rates_does_not_extra_query(
    django_user_client, graphql_client_with_queries
):
    """A target with no rates should resolve in the same query budget as one with
    rates — the metadata row simply doesn't exist yet, and `Coalesce` returns the
    zero defaults without an extra round trip."""
    target_with_rates = django_user_client.user
    for _ in range(3):
        RateFactory(target=target_with_rates, user=UserFactory(), value=4)

    ContentType.objects.clear_cache()
    response_with, queries_with = graphql_client_with_queries(
        COUNTS_ONLY_QUERY, variables={"id": target_with_rates.relay_id}
    )
    assert response_with.json()["data"]["node"]["ratingsCount"] == 3

    target_empty = UserFactory()

    ContentType.objects.clear_cache()
    response_empty, queries_empty = graphql_client_with_queries(
        COUNTS_ONLY_QUERY, variables={"id": target_empty.relay_id}
    )
    assert response_empty.json()["data"]["node"]["ratingsCount"] == 0

    # Empty / populated targets share the same query plan.
    assert queries_empty.count == queries_with.count
