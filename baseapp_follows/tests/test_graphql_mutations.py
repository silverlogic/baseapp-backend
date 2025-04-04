import pytest
import swapper

from baseapp_profiles.tests.factories import ProfileFactory

Follow = swapper.load_model("baseapp_follows", "Follow")

pytestmark = pytest.mark.django_db

FOLLOW_TOGGLE_GRAPHQL = """
mutation FollowToggle($input: FollowToggleInput!) {
  followToggle(input: $input) {
    follow {
      node {
        id
      }
    }
    target {
      id
      followersCount
    }
    actor {
      id
      followingCount
    }
  }
}
"""


def test_anon_cant_follow(graphql_client):
    profile1 = ProfileFactory()
    profile2 = ProfileFactory()

    variables = {
        "input": {
            "actorObjectId": profile1.relay_id,
            "targetObjectId": profile2.relay_id,
        }
    }

    response = graphql_client(FOLLOW_TOGGLE_GRAPHQL, variables=variables)

    content = response.json()
    assert content["errors"][0]["message"] == "authentication required"
    assert Follow.objects.count() == 0


def test_user_can_follow(django_user_client, graphql_user_client):
    profile1 = ProfileFactory(owner=django_user_client.user)
    profile2 = ProfileFactory()

    variables = {
        "input": {
            "actorObjectId": profile1.relay_id,
            "targetObjectId": profile2.relay_id,
        }
    }

    response = graphql_user_client(FOLLOW_TOGGLE_GRAPHQL, variables=variables)

    content = response.json()
    assert content["data"]["followToggle"]["target"]["followersCount"] == 1
    assert content["data"]["followToggle"]["actor"]["followingCount"] == 1


def test_user_can_unfollow(django_user_client, graphql_user_client):
    profile1 = ProfileFactory(owner=django_user_client.user)
    profile2 = ProfileFactory()

    variables = {
        "input": {
            "actorObjectId": profile1.relay_id,
            "targetObjectId": profile2.relay_id,
        }
    }

    response = graphql_user_client(FOLLOW_TOGGLE_GRAPHQL, variables=variables)
    content = response.json()

    assert content["data"]["followToggle"]["target"]["followersCount"] == 1
    assert content["data"]["followToggle"]["actor"]["followingCount"] == 1

    response = graphql_user_client(FOLLOW_TOGGLE_GRAPHQL, variables=variables)
    content = response.json()

    assert content["data"]["followToggle"]["target"]["followersCount"] == 0
    assert content["data"]["followToggle"]["actor"]["followingCount"] == 0


def test_user_cant_unfollow_others_follow(django_user_client, graphql_user_client):
    profile1 = ProfileFactory(owner=django_user_client.user)
    profile2 = ProfileFactory()
    profile3 = ProfileFactory()

    variables = {
        "input": {
            "actorObjectId": profile1.relay_id,
            "targetObjectId": profile2.relay_id,
        }
    }

    response = graphql_user_client(FOLLOW_TOGGLE_GRAPHQL, variables=variables)
    content = response.json()

    assert content["data"]["followToggle"]["target"]["followersCount"] == 1
    assert content["data"]["followToggle"]["actor"]["followingCount"] == 1

    variables = {
        "input": {
            "actorObjectId": profile3.relay_id,
            "targetObjectId": profile2.relay_id,
        }
    }

    response = graphql_user_client(FOLLOW_TOGGLE_GRAPHQL, variables=variables)
    content = response.json()

    assert content["errors"][0]["message"] == "You don't have permission to perform this action"
    assert content["errors"][0]["extensions"]["code"] == "permission_required"
