import pytest

from baseapp_core.tests.factories import UserFactory

from .factories import RateFactory

pytestmark = pytest.mark.django_db

VIEW_QUERY = """
    query GetRate($id: ID!) {
        node(id: $id) {
            ... on RatingsInterface {
                ratingsCount
                ratingsSum
                ratingsAverage
                ratings {
                    edges {
                        node {
                            id
                            value
                        }
                    }
                }
            }
        }
    }
"""


def test_user_can_see_rating_indicators(graphql_user_client):
    user = UserFactory()
    RateFactory(target=user, value=4)
    RateFactory(target=user, value=5)
    response = graphql_user_client(VIEW_QUERY, variables={"id": user.relay_id})
    content = response.json()

    assert content["data"]["node"]["ratingsCount"] == 2
    assert content["data"]["node"]["ratingsSum"] == 9
    assert content["data"]["node"]["ratingsAverage"] == 4.5


def test_user_can_list_ratings(graphql_user_client):
    user = UserFactory()
    RateFactory(target=user, value=4)
    RateFactory(target=user, value=5)
    response = graphql_user_client(VIEW_QUERY, variables={"id": user.relay_id})
    content = response.json()

    assert len(content["data"]["node"]["ratings"]["edges"]) == 2
    assert content["data"]["node"]["ratings"]["edges"][0]["node"]["value"] == 5
    assert content["data"]["node"]["ratings"]["edges"][1]["node"]["value"] == 4
