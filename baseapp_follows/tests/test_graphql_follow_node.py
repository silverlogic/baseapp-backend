"""Follow node fields reached from a FollowToggle payload, on whichever endpoint tests target."""

import pytest

from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

FOLLOW_TOGGLE_GRAPHQL = """
mutation FollowToggle($input: FollowToggleInput!) {
  followToggle(input: $input) {
    follow {
      cursor
      node {
        id
        targetIsFollowingBack
        user { id }
        actorObject { id }
        targetObject { id ... on FollowsInterface { followersCount isFollowedByMe } }
      }
    }
    followDeletedId
  }
}
"""


def test_follow_payload_exposes_follow_fields(django_user_client, graphql_user_client) -> None:
    actor = ProfileFactory(owner=django_user_client.user)
    target = ProfileFactory()
    variables = {"input": {"actorObjectId": actor.relay_id, "targetObjectId": target.relay_id}}

    content = graphql_user_client(FOLLOW_TOGGLE_GRAPHQL, variables=variables).json()

    assert "errors" not in content, content
    payload = content["data"]["followToggle"]
    assert payload["followDeletedId"] is None
    node = payload["follow"]["node"]
    assert node["targetIsFollowingBack"] is False
    assert node["user"]["id"] == django_user_client.user.relay_id
    assert node["actorObject"]["id"] == actor.relay_id
    assert node["targetObject"]["id"] == target.relay_id
    assert node["targetObject"]["followersCount"] == 1

    unfollow = graphql_user_client(FOLLOW_TOGGLE_GRAPHQL, variables=variables).json()
    assert unfollow["data"]["followToggle"]["follow"] is None
    assert unfollow["data"]["followToggle"]["followDeletedId"] == node["id"]
