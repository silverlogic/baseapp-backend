import pytest
import swapper
from baseapp_core.tests.factories import UserFactory

from django.test import override_settings

RateModel = swapper.load_model("baseapp_ratings", "Rate")

pytestmark = pytest.mark.django_db

REACTION_TOGGLE_GRAPHQL = """
    mutation CreateRateMutation($input: CreateRateInput!) {
        createRate(input: $input) {
            rate {
                node {
                    id
                    value
                    target {
                        ... on User {
                            pk
                        }
                    }
                }
            }
        }
    }
"""


def test_anon_cant_rate(graphql_client):
    user = UserFactory()

    response = graphql_client(
        REACTION_TOGGLE_GRAPHQL,
        variables={"input": {"targetObjectId": user.relay_id, "value": 4}},
    )
    content = response.json()
    assert content["errors"][0]["message"] == "authentication required"
    assert RateModel.objects.count() == 0


def test_user_can_add_rate(graphql_user_client):
    user = UserFactory()

    response = graphql_user_client(
        REACTION_TOGGLE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": user.relay_id,
                "value": 4,
            }
        },
    )

    content = response.json()

    assert RateModel.objects.count() == 1
    assert content["data"]["createRate"]["rate"]["node"]["value"] == 4
    assert content["data"]["createRate"]["rate"]["node"]["target"]["pk"] == user.pk


def test_user_cant_add_rate_if_its_higher_than_max_value(graphql_user_client):
    user = UserFactory()

    with override_settings(BASEAPP_MAX_RATING_VALUE=3):
        response = graphql_user_client(
            REACTION_TOGGLE_GRAPHQL,
            variables={
                "input": {
                    "targetObjectId": user.relay_id,
                    "value": 6,
                }
            },
        )

    content = response.json()
    assert RateModel.objects.count() == 0
    assert content["errors"][0]["message"] == "The maximum rating value is 3"
