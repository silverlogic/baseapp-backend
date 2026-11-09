"""Rate node and RatingsInterface contract."""

import pytest
from django.test import override_settings

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import RateFactory

pytestmark = pytest.mark.django_db

RATE_QUERY = """
query Rate($id: ID!) {
    rate(id: $id) {
        id
        value
        user { id }
        profile { id }
        target { id ... on User { pk } }
    }
}
"""

MY_RATING_QUERY = """
query MyRating($id: ID!, $profileId: ID) {
    node(id: $id) {
        ... on RatingsInterface {
            isRatingsEnabled
            myRating(profileId: $profileId) { value }
        }
    }
}
"""

USER_RATINGS_QUERY = """
query UserRatings($id: ID!) {
    node(id: $id) {
        ... on RatingsInterface {
            ratings { edges { node { value target { id } } } }
        }
    }
}
"""


def test_rate_node_exposes_target_user_and_profile(graphql_user_client) -> None:
    target = UserFactory()
    rater = UserFactory()
    profile = ProfileFactory(owner=rater)
    rate = RateFactory(target=target, user=rater, profile=profile, value=3)

    content = graphql_user_client(RATE_QUERY, variables={"id": rate.relay_id}).json()

    assert "errors" not in content, content
    node = content["data"]["rate"]
    assert node["value"] == 3
    assert node["user"]["id"] == rater.relay_id
    assert node["profile"]["id"] == profile.relay_id
    assert node["target"] == {"id": target.relay_id, "pk": target.pk}


def test_my_rating_uses_current_profile_or_given_profile(
    django_user_client, graphql_user_client
) -> None:
    me = django_user_client.user
    target = UserFactory()
    RateFactory(target=target, user=me, profile=me.profile, value=4)

    current = graphql_user_client(MY_RATING_QUERY, variables={"id": target.relay_id}).json()
    explicit = graphql_user_client(
        MY_RATING_QUERY, variables={"id": target.relay_id, "profileId": me.profile.relay_id}
    ).json()

    assert "errors" not in current, current
    assert current["data"]["node"] == {"isRatingsEnabled": True, "myRating": {"value": 4}}
    assert explicit["data"]["node"]["myRating"] == {"value": 4}


@override_settings(ENABLE_PUBLIC_ID_LOGIC=True)
def test_ratings_list_with_targets_is_flat(graphql_client_with_queries) -> None:
    small, big = UserFactory(), UserFactory()
    for _ in range(2):
        RateFactory(target=small, user=UserFactory())
    for _ in range(6):
        RateFactory(target=big, user=UserFactory())

    small_response, small_queries = graphql_client_with_queries(
        USER_RATINGS_QUERY, variables={"id": small.relay_id}
    )
    big_response, big_queries = graphql_client_with_queries(
        USER_RATINGS_QUERY, variables={"id": big.relay_id}
    )

    assert len(small_response.json()["data"]["node"]["ratings"]["edges"]) == 2
    big_edges = big_response.json()["data"]["node"]["ratings"]["edges"]
    assert {e["node"]["target"]["id"] for e in big_edges} == {big.relay_id}
    # `target` is prefetched: no query per row.
    assert big_queries.count == small_queries.count
