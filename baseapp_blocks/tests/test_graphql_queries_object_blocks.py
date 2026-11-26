from django.test import override_settings

"""
Query-count tests for `BlocksInterface`: assert the GraphQL `blockersCount` /
`blockingCount` fields resolve in a flat number of DB queries regardless of how
many `Block` rows point at the target, both on a direct Profile node and on a
nested `block.target.blockersCount` list path.
"""

from collections.abc import Callable

import pytest
from django.http import HttpResponse

from baseapp_core.testing import assert_max_queries, assert_queries_dont_grow
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
# the growth check alone would miss). Bump these deliberately if
# you change the resolver / annotation / middleware path and the new total is
# the new normal — don't bump them to silence a failure without first
# understanding which extra query was added.

# Authenticated superuser, COUNTS_ONLY_QUERY on a Profile node.
EXPECTED_BLOCKS_INTERFACE_QUERY_COUNT = 6

# Regular user, COUNTS_ONLY_QUERY on a Profile node — perm-denied branch.
# A ceiling, because Django's first `has_perm` call loads
# auth_user_user_permissions / auth_group / auth_group_permissions, which can
# vary slightly with Django version and perm-cache behaviour.
EXPECTED_BLOCKS_INTERFACE_PERM_DENIED_UPPER_BOUND = 10

# Authenticated superuser, PROFILE_BLOCKING_LIST_QUERY (nested
# `block.target.blockersCount` on each edge).
EXPECTED_BLOCKS_INTERFACE_NESTED_LIST_QUERY_COUNT = 9


def add_blockers(target) -> Callable[[int], None]:
    """`add_items` for a target's blockers: each new block comes from a new profile."""

    def add(n: int) -> None:
        for _ in range(n):
            actor = ProfileFactory(owner=UserFactory())
            BlockFactory(actor=actor, target=target, user=actor.owner)

    return add


@pytest.fixture
def superuser_client(django_user_client, graphql_user_client) -> Callable[..., HttpResponse]:
    django_user_client.user.is_superuser = True
    django_user_client.user.save()
    return graphql_user_client


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_block_counts_are_flat_regardless_of_block_volume(superuser_client) -> None:
    """`blockersCount` / `blockingCount` on a Profile node take the same number of queries for
    3 blocks as for 20."""
    target = ProfileFactory()
    relay_id = target.relay_id  # resolve outside the capture

    def query() -> HttpResponse:
        return superuser_client(COUNTS_ONLY_QUERY, variables={"id": relay_id})

    assert_queries_dont_grow(
        run=query,
        add_items=add_blockers(target),
        small=3,
        big=20,
        hint="BlockableMetadataService.annotate_queryset is no longer applied to the profile",
    )

    with assert_max_queries(EXPECTED_BLOCKS_INTERFACE_QUERY_COUNT):
        response = query()
    assert response.json()["data"]["node"]["blockersCount"] == 20


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_block_counts_zero_when_no_blocks_does_not_extra_query(superuser_client) -> None:
    """A Profile with no blocks resolves in the same query budget as one with blocks: the
    missing metadata row falls through `Coalesce` to zero."""
    target = ProfileFactory()
    relay_id = target.relay_id

    def query() -> HttpResponse:
        return superuser_client(COUNTS_ONLY_QUERY, variables={"id": relay_id})

    with assert_max_queries(EXPECTED_BLOCKS_INTERFACE_QUERY_COUNT):
        response = query()
    assert response.json()["data"]["node"]["blockersCount"] == 0

    assert_queries_dont_grow(
        run=query,
        add_items=add_blockers(target),
        small=0,
        big=3,
        hint="a missing BlockableMetadata row costs an extra query instead of falling to Coalesce",
    )


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_block_counts_perm_denied_path_is_flat(graphql_user_client) -> None:
    """A non-superuser sees `null` for both counts, and the perm-check path stays flat
    regardless of block volume."""
    target = ProfileFactory()
    relay_id = target.relay_id

    def query() -> HttpResponse:
        return graphql_user_client(COUNTS_ONLY_QUERY, variables={"id": relay_id})

    assert_queries_dont_grow(run=query, add_items=add_blockers(target), small=3, big=20)

    with assert_max_queries(EXPECTED_BLOCKS_INTERFACE_PERM_DENIED_UPPER_BOUND):
        response = query()
    assert response.json()["data"]["node"]["blockersCount"] is None
    assert response.json()["data"]["node"]["blockingCount"] is None


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_block_list_with_target_blockers_count_is_flat(
    django_user_client, superuser_client
) -> None:
    """Listing a Profile's `blocking` connection with `target.blockersCount` on each edge takes
    the same number of queries for 3 blocks as for 20."""
    actor = ProfileFactory(owner=django_user_client.user)
    relay_id = actor.relay_id

    def block(n: int) -> None:
        for _ in range(n):
            target = ProfileFactory(owner=UserFactory())
            BlockFactory(actor=actor, target=target, user=django_user_client.user)

    def query() -> HttpResponse:
        return superuser_client(PROFILE_BLOCKING_LIST_QUERY, variables={"id": relay_id})

    assert_queries_dont_grow(
        run=query,
        add_items=block,
        small=3,
        big=20,
        hint="`target.blockersCount` on each edge is no longer annotated in the list's prefetch",
    )

    with assert_max_queries(EXPECTED_BLOCKS_INTERFACE_NESTED_LIST_QUERY_COUNT):
        response = query()
    assert len(response.json()["data"]["node"]["blocking"]["edges"]) == 20
