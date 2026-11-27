from django.test import override_settings

"""
Query-count tests for the FollowsInterface.

These tests follow the same pattern as
`baseapp_comments/tests/test_graphql_queries_object_comments.py`: they exercise the
GraphQL `FollowsInterface` against a target object (a `Profile` here) and assert that
the number of database queries does NOT scale with the number of follow rows. The goal is
to lock in the query count for the optimizer + `FollowableMetadata` lookup paths and
catch regressions early.

If a test currently fails on count, leave it failing — the assertions encode the *target*
shape, not the present-state shape, and the optimizer/resolver work to reach those numbers
is intentionally not done yet.
"""

from collections.abc import Callable

import pytest
from django.http import HttpResponse

from baseapp_core.testing import assert_max_queries, assert_queries_dont_grow
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import FollowFactory

pytestmark = pytest.mark.django_db


# PAGINATED_FOLLOWERS_QUERY for one page, whatever its size.
PAGINATED_FOLLOWERS_QUERY_COUNT = 11

# Just the followers/following counts (cheapest path; should resolve from
# FollowableMetadata via a single DocumentId join).
COUNTS_ONLY_QUERY = """
    query GetProfile($id: ID!) {
        node(id: $id) {
            ... on FollowsInterface {
                followersCount
                followingCount
            }
        }
    }
"""


# Counts plus the follower edges on a target profile — the bread-and-butter screen for a
# "who follows me" list. Each follower edge exposes the actor profile (one extra hop via
# DocumentId.content_object).
FOLLOWERS_LIST_QUERY = """
    query GetProfile($id: ID!) {
        node(id: $id) {
            ... on FollowsInterface {
                followersCount
                followers {
                    edges {
                        node {
                            id
                            targetIsFollowingBack
                            actorObject {
                                id
                            }
                        }
                    }
                }
            }
        }
    }
"""


# Same shape but for "who I'm following".
FOLLOWING_LIST_QUERY = """
    query GetProfile($id: ID!) {
        node(id: $id) {
            ... on FollowsInterface {
                followingCount
                following {
                    edges {
                        node {
                            id
                            targetIsFollowingBack
                            targetObject {
                                id
                            }
                        }
                    }
                }
            }
        }
    }
"""


# Paginated followers list. Important to assert the count is independent of page size.
PAGINATED_FOLLOWERS_QUERY = """
    query GetProfile($id: ID!, $first: Int, $after: String) {
        node(id: $id) {
            ... on FollowsInterface {
                followersCount
                followers(first: $first, after: $after) {
                    edges {
                        node {
                            id
                            actorObject {
                                id
                            }
                        }
                    }
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                }
            }
        }
    }
"""


# Nested: each follower edge exposes the actor's *own* followersCount. This is the most
# expensive path because it forces the resolver to look up FollowableMetadata for every
# row in the connection. We want the count to stay flat — proportional to the number of
# distinct profiles in the connection, not multiplied per nested field.
NESTED_FOLLOWERS_QUERY = """
    query GetProfile($id: ID!) {
        node(id: $id) {
            ... on FollowsInterface {
                followersCount
                followingCount
                followers {
                    edges {
                        node {
                            id
                            actorObject {
                                id
                                ... on FollowsInterface {
                                    followersCount
                                    followingCount
                                }
                            }
                        }
                    }
                }
            }
        }
    }
"""


def add_followers(target, *, with_own_follower: bool = False) -> Callable[[int], None]:
    """`add_items` for a target's followers. `with_own_follower` gives each new follower a
    follower of its own, so a nested `followersCount` is non-zero."""

    def add(n: int) -> None:
        for _ in range(n):
            user = UserFactory()
            follower = ProfileFactory(owner=user)
            FollowFactory(actor_object=follower, target_object=target, user=user)
            if with_own_follower:
                inner_user = UserFactory()
                inner = ProfileFactory(owner=inner_user)
                FollowFactory(actor_object=inner, target_object=follower, user=inner_user)

    return add


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_followers_and_following_counts_query_count(
    django_user_client, graphql_client
) -> None:
    """Counts-only query: both counts arrive as annotations on the Profile fetch (subqueries
    against follows_followablemetadata), so the whole path is:
    1) DocumentId resolve by public_id (joined to django_content_type)
    2) ContentType lookup for profiles.profile (cold cache)
    3) Profile fetch with _followable_followers_count + _followable_following_count annotated
       via FollowableMetadataService.annotate_queryset
    """
    target_profile = ProfileFactory(owner=django_user_client.user)
    add_followers(target_profile)(3)
    relay_id = target_profile.relay_id  # resolve outside the capture

    with assert_max_queries(3, hint="FollowableMetadataService.annotate_queryset was dropped"):
        response = graphql_client(COUNTS_ONLY_QUERY, variables={"id": relay_id})

    content = response.json()
    assert content["data"]["node"]["followersCount"] == 3
    assert content["data"]["node"]["followingCount"] == 0


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_followers_list_query_count_does_not_grow_with_followers(
    django_user_client, graphql_client
) -> None:
    """Listing followers takes the same queries for 15 followers as for 3."""
    target_profile = ProfileFactory(owner=django_user_client.user)
    relay_id = target_profile.relay_id

    def query() -> HttpResponse:
        return graphql_client(FOLLOWERS_LIST_QUERY, variables={"id": relay_id})

    assert_queries_dont_grow(
        run=query,
        add_items=add_followers(target_profile),
        small=3,
        big=15,
        hint="the followers connection lost its batched actor prefetch",
    )

    assert len(query().json()["data"]["node"]["followers"]["edges"]) == 15


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_following_list_query_count_is_flat(django_user_client, graphql_client) -> None:
    """Symmetric to the followers list: `following` for a profile resolves in a flat number of
    queries.

    Counts-only path is 3 queries (see test_anon_followers_and_following_counts_query_count).
    The following-list path adds, on top of that:
      + ContentType.get for follows.follow
      + COUNT(*) over follows_follow filtered by actor_id
      + the connection fetch (Follow rows with mapped_public_id annotated)
      + GenericPrefetch's batched DocumentId fetch for actor (1 query)
      + GenericPrefetch's batched Profile fetch for actor (1 query, all rows in one IN())
      + same pair for target (DocumentIds + Profiles batched)
    Total = 3 + 8 = 11, independent of how many follow rows exist.
    """
    actor_profile = ProfileFactory(owner=django_user_client.user)
    relay_id = actor_profile.relay_id

    def follow(n: int) -> None:
        for _ in range(n):
            target = ProfileFactory(owner=UserFactory())
            FollowFactory(
                actor_object=actor_profile, target_object=target, user=actor_profile.owner
            )

    def query() -> HttpResponse:
        return graphql_client(FOLLOWING_LIST_QUERY, variables={"id": relay_id})

    assert_queries_dont_grow(
        run=query,
        add_items=follow,
        small=1,
        big=5,
        hint="the following connection lost its batched target prefetch",
    )

    with assert_max_queries(11):
        response = query()
    content = response.json()
    assert content["data"]["node"]["followingCount"] == 5
    assert len(content["data"]["node"]["following"]["edges"]) == 5


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_followers_pagination_query_count_independent_of_page_size(
    django_user_client, graphql_client
) -> None:
    """A page of 50 followers takes the same queries as a page of 5. Catches a resolver that
    fans out per-edge queries."""
    target_profile = ProfileFactory(owner=django_user_client.user)
    # 60 followers + Faker's `email` provider draws from a finite pool, so unique-email
    # collisions become routine at this volume (and stick around across --reuse-db
    # runs). Build deterministic emails namespaced by the target profile's pk so they
    # stay unique across runs and across other tests that share the test DB.
    for i in range(60):
        u = UserFactory(email=f"follower-{target_profile.pk}-{i}@example.com")
        fp = ProfileFactory(owner=u)
        FollowFactory(actor_object=fp, target_object=target_profile, user=u)
    relay_id = target_profile.relay_id

    for first in (5, 50):
        with assert_max_queries(PAGINATED_FOLLOWERS_QUERY_COUNT, hint=f"page size {first}"):
            response = graphql_client(
                PAGINATED_FOLLOWERS_QUERY, variables={"id": relay_id, "first": first}
            )
        followers = response.json()["data"]["node"]["followers"]
        assert len(followers["edges"]) == first
        assert followers["pageInfo"]["hasNextPage"] is True


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_nested_followers_count_does_not_explode(django_user_client, graphql_client) -> None:
    """When each follower edge expands to its own followers/following counts, the count stays
    flat (one batch fetch, not one per row). This is the canonical 'N+1 on
    FollowableMetadata' regression test."""
    target_profile = ProfileFactory(owner=django_user_client.user)
    relay_id = target_profile.relay_id

    def query() -> HttpResponse:
        return graphql_client(NESTED_FOLLOWERS_QUERY, variables={"id": relay_id})

    assert_queries_dont_grow(
        run=query,
        add_items=add_followers(target_profile, with_own_follower=True),
        small=5,
        big=10,
        hint="the nested followersCount is no longer annotated on the followers' profiles",
    )

    edges = query().json()["data"]["node"]["followers"]["edges"]
    assert [e["node"]["actorObject"]["followersCount"] for e in edges] == [1] * 10
