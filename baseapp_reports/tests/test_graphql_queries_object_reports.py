"""
Query-count tests for the `ReportsInterface`.

Mirrors `baseapp_follows/tests/test_graphql_queries_object_follows.py` and
`baseapp_comments/tests/test_graphql_queries_object_comments.py`: exercise the
GraphQL `ReportsInterface` against a target object (a `Profile`) and assert that the
number of database queries does NOT scale with the number of report rows. The goal is
to lock in the query count for the `reportable_metadata` annotation path and catch
regressions early — particularly the broken `Coalesce(KeyTextTransform, Value("0"))`
mix that briefly leaked through the optimizer.
"""

import pytest
from constance.test import override_config
from django.contrib.contenttypes.models import ContentType

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import ReportFactory, ReportTypeFactory

pytestmark = pytest.mark.django_db


# Baseline for `reportsCount` on one Profile node: 1× relay `node()` (documentid +
# content_type JOIN) + 1× `profiles_profile` load with `ReportableMetadata` inlined
# as a Subquery via `pre_optimization_hook`.
# Update this number deliberately if you change the resolver / annotation path.
EXPECTED_REPORTS_INTERFACE_QUERY_COUNT = 2


# Counts-only query: should resolve from `ReportableMetadata` via a single annotated
# subquery on the Profile fetch.
COUNTS_ONLY_QUERY = """
    query GetProfile($id: ID!) {
        node(id: $id) {
            ... on ReportsInterface {
                reportsCount
            }
        }
    }
"""


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_reports_count_is_flat_regardless_of_report_volume(
    django_user_client, graphql_client_with_queries
):
    """`reportsCount` should be a flat query path: regardless of how many `Report`
    rows point at the target, the GraphQL query should make the same number of DB
    round-trips. This locks in the `ReportableMetadataService.annotate_queryset`
    optimisation."""
    target_small = ProfileFactory(owner=django_user_client.user)
    spam_type = ReportTypeFactory(key="spam_query", label="Spam query")
    for _ in range(3):
        ReportFactory(user=UserFactory(), target=target_small, report_type=spam_type)

    ContentType.objects.clear_cache()
    response_small, queries_small = graphql_client_with_queries(
        COUNTS_ONLY_QUERY, variables={"id": target_small.relay_id}
    )
    assert response_small.json()["data"]["node"]["reportsCount"]["total"] == 3
    small_count = queries_small.count

    # Now create a fresh target with way more reports and run the same query.
    big_target = ProfileFactory(owner=UserFactory())
    for _ in range(20):
        ReportFactory(user=UserFactory(), target=big_target, report_type=spam_type)

    ContentType.objects.clear_cache()
    response_big, queries_big = graphql_client_with_queries(
        COUNTS_ONLY_QUERY, variables={"id": big_target.relay_id}
    )
    assert response_big.json()["data"]["node"]["reportsCount"]["total"] == 20

    # Hard invariant: the optimizer should NOT issue more queries when there are 20
    # reports vs. 3. Counts come from a single annotated subquery against
    # `reports_reportablemetadata` on the Profile fetch.
    assert queries_big.count == small_count
    # Absolute baseline, catches regressions that bump both sides together.
    assert small_count == EXPECTED_REPORTS_INTERFACE_QUERY_COUNT


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_reports_count_zero_when_no_reports_does_not_extra_query(
    django_user_client, graphql_client_with_queries
):
    """When a profile has no reports, `reportsCount` should still resolve in the
    same query budget as a profile with reports — the metadata row simply doesn't
    exist yet, and the annotated COALESCE returns the default `{"total": 0}` dict
    without an extra round trip."""
    target_with_reports = ProfileFactory(owner=django_user_client.user)
    rt = ReportTypeFactory(key="rc_q1", label="rc_q1")
    for _ in range(3):
        ReportFactory(user=UserFactory(), target=target_with_reports, report_type=rt)

    ContentType.objects.clear_cache()
    response_with, queries_with = graphql_client_with_queries(
        COUNTS_ONLY_QUERY, variables={"id": target_with_reports.relay_id}
    )
    assert response_with.json()["data"]["node"]["reportsCount"]["total"] == 3

    target_empty = ProfileFactory(owner=UserFactory())

    ContentType.objects.clear_cache()
    response_empty, queries_empty = graphql_client_with_queries(
        COUNTS_ONLY_QUERY, variables={"id": target_empty.relay_id}
    )
    assert response_empty.json()["data"]["node"]["reportsCount"]["total"] == 0

    # Both paths annotate the same subquery; absence of the metadata row falls back to
    # the default JSON via `COALESCE`, no extra query.
    assert queries_empty.count == queries_with.count
    # Absolute baseline, same expected count as the populated path.
    assert queries_empty.count == EXPECTED_REPORTS_INTERFACE_QUERY_COUNT
