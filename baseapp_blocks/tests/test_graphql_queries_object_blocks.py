"""
Query-count tests for the `BlocksInterface`.

Mirrors `baseapp_reactions/tests/test_graphql_queries_object_reactions.py`: assert
the GraphQL `BlocksInterface` resolves in a flat number of database queries
regardless of how many `Block` rows exist for the target — locks in the
`BlockableMetadataService.annotate_queryset` optimisation and catches
`Coalesce` / annotation-removal regressions in the read path.

Each test promotes the `django_user_client` user to `is_superuser=True` so the
per-field perm checks in `BlocksInterface.resolve_*` pass; otherwise an anon
user would see `null` counts and the metadata read would never run.
"""

import pytest
from constance.test import override_config
from django.contrib.contenttypes.models import ContentType

from baseapp_core.graphql.utils import capture_database_queries
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import BlockFactory

pytestmark = pytest.mark.django_db


# Baseline for `blockersCount` + `blockingCount` on one Profile node when the
# requesting client is an authenticated superuser:
#   1) django_session (session middleware)
#   2) users_user (request.user load)
#   3) profiles_profile minimal fetch (current_profile middleware sets
#      request.user.current_profile = request.user.profile)
#   4) baseapp_core_documentid lookup by public_id (relay GlobalID resolution)
#   5) ContentType lookup for profiles.profile (cache cleared at top of test)
#   6) profiles_profile with all pre_optimization_hook metadata Subqueries
#      inlined (commentable + followable + reportable + blockable + ratable)
#      — counts come back from this same SELECT, no extra per-row fetch.
# Items 1-3 are session/auth/current_profile middleware overhead that fires
# on every authenticated request and is unrelated to the BlocksInterface;
# items 4-6 are the irreducible relay-node + optimized-fetch path.
# Update this number deliberately if you change the resolver / annotation path.
EXPECTED_BLOCKS_INTERFACE_QUERY_COUNT = 6

# Upper bound for the perm-denied path (regular user). Higher than the superuser
# baseline because Django short-circuits `has_perm` for superusers, while
# non-superusers load `auth_user_user_permissions`, `auth_group`, and
# `auth_group_permissions` on the first `has_perm` call (Django caches them on
# the user instance, so subsequent calls in the same request are free).
# Headroom over the observed value accommodates Django version / perm-cache drift.
EXPECTED_BLOCKS_INTERFACE_PERM_DENIED_UPPER_BOUND = 10


COUNTS_ONLY_QUERY = """
    query GetTarget($id: ID!) {
        node(id: $id) {
            ... on BlocksInterface {
                blockersCount
                blockingCount
            }
        }
    }
"""


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_block_counts_are_flat_regardless_of_block_volume(django_user_client, graphql_user_client):
    """`blockersCount` / `blockingCount` should be a flat query path: regardless
    of how many `Block` rows point at the target, the GraphQL query should make
    the same number of DB round-trips (modulo content-type cache jitter)."""
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    target_small = ProfileFactory()
    for _ in range(3):
        actor = ProfileFactory(owner=UserFactory())
        BlockFactory(actor=actor, target=target_small, user=actor.owner)
    small_relay_id = target_small.relay_id  # resolve outside `capture_database_queries`

    ContentType.objects.clear_cache()
    with capture_database_queries() as queries_small:
        response_small = graphql_user_client(COUNTS_ONLY_QUERY, variables={"id": small_relay_id})
    assert response_small.json()["data"]["node"]["blockersCount"] == 3
    small_count = queries_small.count

    big_target = ProfileFactory()
    for _ in range(20):
        actor = ProfileFactory(owner=UserFactory())
        BlockFactory(actor=actor, target=big_target, user=actor.owner)
    big_relay_id = big_target.relay_id

    ContentType.objects.clear_cache()
    with capture_database_queries() as queries_big:
        response_big = graphql_user_client(COUNTS_ONLY_QUERY, variables={"id": big_relay_id})
    assert response_big.json()["data"]["node"]["blockersCount"] == 20

    assert queries_big.count == small_count
    # Absolute baseline, catches regressions that bump both sides together.
    assert small_count == EXPECTED_BLOCKS_INTERFACE_QUERY_COUNT


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_block_counts_zero_when_no_blocks_does_not_extra_query(
    django_user_client, graphql_user_client
):
    """A profile with no blocks should resolve in the same query budget as one
    with blocks — the metadata row simply doesn't exist yet, and `Coalesce`
    returns the zero defaults without an extra round trip."""
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    target_with_blocks = ProfileFactory()
    for _ in range(3):
        actor = ProfileFactory(owner=UserFactory())
        BlockFactory(actor=actor, target=target_with_blocks, user=actor.owner)
    with_blocks_relay_id = target_with_blocks.relay_id

    ContentType.objects.clear_cache()
    with capture_database_queries() as queries_with:
        response_with = graphql_user_client(
            COUNTS_ONLY_QUERY, variables={"id": with_blocks_relay_id}
        )
    assert response_with.json()["data"]["node"]["blockersCount"] == 3

    target_empty = ProfileFactory()
    empty_relay_id = target_empty.relay_id

    ContentType.objects.clear_cache()
    with capture_database_queries() as queries_empty:
        response_empty = graphql_user_client(COUNTS_ONLY_QUERY, variables={"id": empty_relay_id})
    assert response_empty.json()["data"]["node"]["blockersCount"] == 0

    assert queries_empty.count == queries_with.count
    # Absolute baseline, same expected count as the populated path.
    assert queries_empty.count == EXPECTED_BLOCKS_INTERFACE_QUERY_COUNT


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_block_counts_perm_denied_path_is_flat(graphql_user_client):
    """Regular (non-superuser) viewer should hit the perm-denied branch in each
    `BlocksInterface.resolve_*_count` resolver — `has_perm` returns False, the
    resolver returns `None`, and the GraphQL field comes back as `null`. The
    important invariant here: the perm checks themselves should be cached
    (Django's user permission cache) and not scale with the number of blocks
    on the target."""
    target_small = ProfileFactory()
    for _ in range(3):
        actor = ProfileFactory(owner=UserFactory())
        BlockFactory(actor=actor, target=target_small, user=actor.owner)
    small_relay_id = target_small.relay_id

    ContentType.objects.clear_cache()
    with capture_database_queries() as queries_small:
        response_small = graphql_user_client(COUNTS_ONLY_QUERY, variables={"id": small_relay_id})
    assert response_small.json()["data"]["node"]["blockersCount"] is None
    assert response_small.json()["data"]["node"]["blockingCount"] is None

    big_target = ProfileFactory()
    for _ in range(20):
        actor = ProfileFactory(owner=UserFactory())
        BlockFactory(actor=actor, target=big_target, user=actor.owner)
    big_relay_id = big_target.relay_id

    ContentType.objects.clear_cache()
    with capture_database_queries() as queries_big:
        response_big = graphql_user_client(COUNTS_ONLY_QUERY, variables={"id": big_relay_id})
    assert response_big.json()["data"]["node"]["blockersCount"] is None

    # Flat regardless of block volume — catches regressions where perm checking
    # starts iterating over `Block` rows or re-fetching ContentType per call.
    assert queries_big.count == queries_small.count
    assert queries_small.count <= EXPECTED_BLOCKS_INTERFACE_PERM_DENIED_UPPER_BOUND
