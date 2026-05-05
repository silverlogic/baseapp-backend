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

import pytest
from constance.test import override_config
from django.contrib.contenttypes.models import ContentType

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import FollowFactory

pytestmark = pytest.mark.django_db


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


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_followers_and_following_counts_query_count(
    django_user_client, graphql_client_with_queries
):
    """Counts-only query: should be flat regardless of follower volume."""
    target_profile = ProfileFactory(owner=django_user_client.user)
    follower_users = [UserFactory() for _ in range(3)]
    follower_profiles = [ProfileFactory(owner=u) for u in follower_users]
    for fp in follower_profiles:
        FollowFactory(actor_object=fp, target_object=target_profile, user=fp.owner)

    ContentType.objects.clear_cache()

    response, queries = graphql_client_with_queries(
        COUNTS_ONLY_QUERY, variables={"id": target_profile.relay_id}
    )
    content = response.json()

    assert content["data"]["node"]["followersCount"] == 3
    assert content["data"]["node"]["followingCount"] == 0

    # Both counts arrive as annotations on the Profile fetch (subqueries against
    # follows_followablemetadata), so the whole counts-only path is just:
    # 1) DocumentId resolve by public_id (joined to django_content_type)
    # 2) Profile fetch with _followable_followers_count + _followable_following_count
    #    annotated via FollowableMetadataService.annotate_queryset
    assert queries.count == 2


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_followers_list_query_count_does_not_grow_with_followers(
    django_user_client, graphql_client_with_queries
):
    """Listing followers should be O(1) in the optimizer's eyes regardless of how many
    follower rows exist. Two test runs with different follower counts must produce the
    same query count (this is the regression we want to lock in)."""
    target_profile = ProfileFactory(owner=django_user_client.user)

    follower_users_small = [UserFactory() for _ in range(3)]
    for u in follower_users_small:
        fp = ProfileFactory(owner=u)
        FollowFactory(actor_object=fp, target_object=target_profile, user=u)

    ContentType.objects.clear_cache()
    response_small, queries_small = graphql_client_with_queries(
        FOLLOWERS_LIST_QUERY, variables={"id": target_profile.relay_id}
    )
    assert (
        len(response_small.json()["data"]["node"]["followers"]["edges"]) == 3
    ), response_small.json()
    small_count = queries_small.count

    # Now create a second target with many more followers and run the same query.
    big_target = ProfileFactory(owner=UserFactory())
    follower_users_big = [UserFactory() for _ in range(15)]
    for u in follower_users_big:
        fp = ProfileFactory(owner=u)
        FollowFactory(actor_object=fp, target_object=big_target, user=u)

    ContentType.objects.clear_cache()
    response_big, queries_big = graphql_client_with_queries(
        FOLLOWERS_LIST_QUERY, variables={"id": big_target.relay_id}
    )
    assert len(response_big.json()["data"]["node"]["followers"]["edges"]) == 15

    # The whole point of the optimizer: query count must NOT grow with row count.
    assert queries_big.count == small_count


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_following_list_query_count_is_flat(django_user_client, graphql_client_with_queries):
    """Symmetric to followers list — querying `following` for a profile should also
    resolve in a flat number of queries."""
    actor_profile = ProfileFactory(owner=django_user_client.user)
    target_profiles = [ProfileFactory(owner=UserFactory()) for _ in range(5)]
    for tp in target_profiles:
        FollowFactory(actor_object=actor_profile, target_object=tp, user=actor_profile.owner)

    ContentType.objects.clear_cache()
    response, queries = graphql_client_with_queries(
        FOLLOWING_LIST_QUERY, variables={"id": actor_profile.relay_id}
    )
    content = response.json()

    assert content["data"]["node"]["followingCount"] == 5
    assert len(content["data"]["node"]["following"]["edges"]) == 5

    # Counts-only path is 2 queries (see test_anon_followers_and_following_counts_query_count).
    # The following-list path adds, on top of that:
    #   + ContentType.get for follows.follow (cleared above)
    #   + COUNT(*) over follows_follow filtered by actor_id
    #   + the connection fetch (Follow rows with mapped_public_id annotated)
    #   + GenericPrefetch's batched DocumentId fetch for actor (1 query)
    #   + GenericPrefetch's batched Profile fetch for actor (1 query, all rows in one IN())
    #   + same pair for target (DocumentIds + Profiles batched)
    # Total = 2 + 8 = 10. Independent of how many follow rows exist.
    assert queries.count == 10


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_followers_pagination_query_count_independent_of_page_size(
    django_user_client, graphql_client_with_queries
):
    """The paginated followers query should not scale with the page size — first=50 must
    use the same number of queries (within ContentType-cache jitter) as first=5.
    Catches a regression where the resolver fans out per-edge queries."""
    target_profile = ProfileFactory(owner=django_user_client.user)
    for _ in range(60):
        u = UserFactory()
        fp = ProfileFactory(owner=u)
        FollowFactory(actor_object=fp, target_object=target_profile, user=u)

    ContentType.objects.clear_cache()
    resp_small, q_small = graphql_client_with_queries(
        PAGINATED_FOLLOWERS_QUERY, variables={"id": target_profile.relay_id, "first": 5}
    )
    assert len(resp_small.json()["data"]["node"]["followers"]["edges"]) == 5
    assert resp_small.json()["data"]["node"]["followers"]["pageInfo"]["hasNextPage"] is True

    ContentType.objects.clear_cache()
    resp_big, q_big = graphql_client_with_queries(
        PAGINATED_FOLLOWERS_QUERY, variables={"id": target_profile.relay_id, "first": 50}
    )
    assert len(resp_big.json()["data"]["node"]["followers"]["edges"]) == 50
    assert resp_big.json()["data"]["node"]["followers"]["pageInfo"]["hasNextPage"] is True

    # 10× the page size, only ContentType-cache-warming jitter (one extra
    # `ContentType.objects.get_for_model` per cache wipe). The invariant we care about
    # is that the gap between the two runs stays bounded — definitively NOT 10× the page
    # multiplier.
    assert abs(q_big.count - q_small.count) <= 1


@override_config(ENABLE_PUBLIC_ID_LOGIC=True)
def test_anon_nested_followers_count_does_not_explode(
    django_user_client, graphql_client_with_queries
):
    """When each follower edge expands to its own followers/following counts, query count
    should stay sublinear (one extra batch fetch — not one per row). This is the canonical
    'N+1 on FollowableMetadata' regression test."""
    target_profile = ProfileFactory(owner=django_user_client.user)
    follower_profiles = []
    for _ in range(5):
        u = UserFactory()
        fp = ProfileFactory(owner=u)
        FollowFactory(actor_object=fp, target_object=target_profile, user=u)
        follower_profiles.append(fp)

    # Give one of the followers their OWN follower so followersCount is non-zero — keeps
    # the assertion meaningful (otherwise we'd be checking that 0 == 0 N times).
    extra_follower_user = UserFactory()
    extra_follower_profile = ProfileFactory(owner=extra_follower_user)
    FollowFactory(
        actor_object=extra_follower_profile,
        target_object=follower_profiles[0],
        user=extra_follower_user,
    )

    ContentType.objects.clear_cache()
    response_small, queries_small = graphql_client_with_queries(
        NESTED_FOLLOWERS_QUERY, variables={"id": target_profile.relay_id}
    )
    content = response_small.json()
    assert len(content["data"]["node"]["followers"]["edges"]) == 5
    nested_followers_counts = [
        e["node"]["actorObject"]["followersCount"]
        for e in content["data"]["node"]["followers"]["edges"]
    ]
    # One follower has followersCount=1, the rest 0.
    assert sorted(nested_followers_counts) == [0, 0, 0, 0, 1]
    small_count = queries_small.count

    # Now run the same query with double the followers. The query count must NOT double.
    target_profile_big = ProfileFactory(owner=UserFactory())
    big_followers = []
    for _ in range(10):
        u = UserFactory()
        fp = ProfileFactory(owner=u)
        FollowFactory(actor_object=fp, target_object=target_profile_big, user=u)
        big_followers.append(fp)
    # Give a few of them inner-followers to keep counts non-zero
    for fp in big_followers[:3]:
        u = UserFactory()
        inner = ProfileFactory(owner=u)
        FollowFactory(actor_object=inner, target_object=fp, user=u)

    ContentType.objects.clear_cache()
    response_big, queries_big = graphql_client_with_queries(
        NESTED_FOLLOWERS_QUERY, variables={"id": target_profile_big.relay_id}
    )
    assert len(response_big.json()["data"]["node"]["followers"]["edges"]) == 10

    # The actual numeric count is encoded in queries_small/queries_big. The invariant we
    # care about: doubling the rows does not double the queries.
    assert queries_big.count == small_count
