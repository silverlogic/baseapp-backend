from django.test import override_settings

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
from django.http import HttpResponse

from baseapp_core.testing import assert_max_queries, assert_queries_dont_grow
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import ReportFactory, ReportTypeFactory

pytestmark = pytest.mark.django_db


# Baseline for `reportsCount` on one Profile node: relay `node()` (documentid +
# content_type JOIN) + `profiles_profile` load with `ReportableMetadata` inlined
# as a Subquery via `pre_optimization_hook`.
# The Profile ContentType lookup counts too: `assert_max_queries` starts from a cold
# ContentType cache, so the number doesn't depend on which tests ran first.
# Update this number deliberately if you change the resolver / annotation path.
EXPECTED_REPORTS_INTERFACE_QUERY_COUNT = 3


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


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_reports_count_is_flat_regardless_of_report_volume(graphql_client) -> None:
    """`reportsCount` comes from one annotated subquery against `reports_reportablemetadata` on
    the Profile fetch: 20 reports take the same queries as 3."""
    target = ProfileFactory(owner=UserFactory())
    spam_type = ReportTypeFactory(key="spam_query", label="Spam query")

    relay_id = target.relay_id  # resolve outside the capture

    def query() -> HttpResponse:
        return graphql_client(COUNTS_ONLY_QUERY, variables={"id": relay_id})

    assert_queries_dont_grow(
        run=query,
        add_items=lambda n: [
            ReportFactory(user=UserFactory(), target=target, report_type=spam_type)
            for _ in range(n)
        ],
        small=3,
        big=20,
        hint="ReportableMetadataService.annotate_queryset is no longer applied to the profile",
    )

    # Absolute baseline, catches regressions that bump both sides together.
    with assert_max_queries(EXPECTED_REPORTS_INTERFACE_QUERY_COUNT):
        response = query()
    assert response.json()["data"]["node"]["reportsCount"]["total"] == 20


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_reports_count_zero_when_no_reports_does_not_extra_query(graphql_client) -> None:
    """A profile with no reports resolves in the same budget as one with reports: the metadata
    row doesn't exist yet, and COALESCE returns the default `{"total": 0}` without an extra
    round trip."""
    target = ProfileFactory(owner=UserFactory())
    rt = ReportTypeFactory(key="rc_q1", label="rc_q1")

    relay_id = target.relay_id  # resolve outside the capture

    def query() -> HttpResponse:
        return graphql_client(COUNTS_ONLY_QUERY, variables={"id": relay_id})

    with assert_max_queries(EXPECTED_REPORTS_INTERFACE_QUERY_COUNT):
        response = query()
    assert response.json()["data"]["node"]["reportsCount"]["total"] == 0

    assert_queries_dont_grow(
        run=query,
        add_items=lambda n: [
            ReportFactory(user=UserFactory(), target=target, report_type=rt) for _ in range(n)
        ],
        small=0,
        big=3,
        hint="a missing ReportableMetadata row costs an extra query instead of falling to COALESCE",
    )
