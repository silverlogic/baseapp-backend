"""
Query-count tests for `BlocksInterface`: assert the GraphQL `blockersCount` /
`blockingCount` fields resolve in a flat number of DB queries regardless of how
many `Block` rows point at the target, both on a direct Profile node and on a
nested `block.target.blockersCount` list path.
"""

import pytest
from constance.test import override_config
from django.contrib.contenttypes.models import ContentType

from baseapp_core.graphql.utils import capture_database_queries
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import BlockFactory

pytestmark = pytest.mark.django_db


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

PROFILE_BLOCKING_LIST_QUERY = """
    query ProfileBlocking($id: ID!) {
        node(id: $id) {
            ... on BlocksInterface {
                blocking {
                    edges {
                        node {
                            id
                            target {
                                id
                                blockersCount
                            }
                        }
                    }
                }
            }
        }
    }
"""


# Absolute query budgets for the COUNTS_ONLY_QUERY path. These guard against
# regressions where BOTH the small- and big-volume counts bump together (which
# the per-test `big == small` assertion would miss). Bump these deliberately if
# you change the resolver / annotation / middleware path and the new total is
# the new normal — don't bump them to silence a failure without first
# understanding which extra query was added.

# Authenticated superuser, COUNTS_ONLY_QUERY on a Profile node.
EXPECTED_BLOCKS_INTERFACE_QUERY_COUNT = 6

# Regular user, COUNTS_ONLY_QUERY on a Profile node — perm-denied branch.
# Upper bound (not equality) because Django's first `has_perm` call loads
# auth_user_user_permissions / auth_group / auth_group_permissions, which can
# vary slightly with Django version and perm-cache behaviour.
EXPECTED_BLOCKS_INTERFACE_PERM_DENIED_UPPER_BOUND = 10

# Authenticated superuser, PROFILE_BLOCKING_LIST_QUERY (nested
# `block.target.blockersCount` on each edge).
EXPECTED_BLOCKS_INTERFACE_NESTED_LIST_QUERY_COUNT = 9


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_block_counts_are_flat_regardless_of_block_volume(
    django_user_client, graphql_user_client
) -> None:
    """`blockersCount` / `blockingCount` on a Profile node take the same number
    of queries for 3 blocks as for 20."""
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
    assert small_count == EXPECTED_BLOCKS_INTERFACE_QUERY_COUNT


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_block_counts_zero_when_no_blocks_does_not_extra_query(
    django_user_client, graphql_user_client
) -> None:
    """A Profile with no blocks resolves in the same query budget as one with
    blocks — the missing metadata row falls through `Coalesce` to zero."""
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
    assert queries_empty.count == EXPECTED_BLOCKS_INTERFACE_QUERY_COUNT


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_block_counts_perm_denied_path_is_flat(graphql_user_client) -> None:
    """A non-superuser sees `null` for both counts and the perm-check path
    stays flat regardless of block volume."""
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

    assert queries_big.count == queries_small.count
    assert queries_small.count <= EXPECTED_BLOCKS_INTERFACE_PERM_DENIED_UPPER_BOUND


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_block_list_with_target_blockers_count_is_flat(
    django_user_client, graphql_user_client
) -> None:
    """Listing a Profile's `blocking` connection with `target.blockersCount` on
    each edge takes the same number of queries for 3 blocks as for 20."""
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    actor = ProfileFactory(owner=django_user_client.user)
    for _ in range(3):
        target = ProfileFactory(owner=UserFactory())
        BlockFactory(actor=actor, target=target, user=django_user_client.user)
    actor_relay_id = actor.relay_id

    ContentType.objects.clear_cache()
    with capture_database_queries() as queries_small:
        r_small = graphql_user_client(PROFILE_BLOCKING_LIST_QUERY, variables={"id": actor_relay_id})
    assert "errors" not in r_small.json(), r_small.json()
    assert len(r_small.json()["data"]["node"]["blocking"]["edges"]) == 3
    small_count = queries_small.count

    for _ in range(17):
        target = ProfileFactory(owner=UserFactory())
        BlockFactory(actor=actor, target=target, user=django_user_client.user)

    ContentType.objects.clear_cache()
    with capture_database_queries() as queries_big:
        r_big = graphql_user_client(PROFILE_BLOCKING_LIST_QUERY, variables={"id": actor_relay_id})
    assert "errors" not in r_big.json(), r_big.json()
    assert len(r_big.json()["data"]["node"]["blocking"]["edges"]) == 20
    big_count = queries_big.count

    assert big_count == small_count, (
        f"N+1: {small_count} queries for 3 blocks vs {big_count} for 20 "
        f"(delta {big_count - small_count} over 17 extra blocks = "
        f"{(big_count - small_count) / 17:.1f} per row)"
    )
    assert small_count == EXPECTED_BLOCKS_INTERFACE_NESTED_LIST_QUERY_COUNT
