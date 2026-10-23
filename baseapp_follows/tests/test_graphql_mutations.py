import pytest
import swapper
from django.conf import settings
from django.test import override_settings

from baseapp_follows.permissions import FollowsPermissionsBackend
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import FollowFactory

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


def test_anon_cant_follow(graphql_client) -> None:
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


def test_user_can_follow(django_user_client, graphql_user_client) -> None:
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


def test_user_can_unfollow(django_user_client, graphql_user_client) -> None:
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


def test_user_cant_unfollow_others_follow(django_user_client, graphql_user_client) -> None:
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


def test_user_can_follow_profile_from_same_user(django_user_client, graphql_user_client) -> None:
    profile1 = ProfileFactory(owner=django_user_client.user)
    profile2 = ProfileFactory(owner=django_user_client.user)

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


def test_user_can_unfollow_profile_from_same_user(django_user_client, graphql_user_client) -> None:
    profile1 = ProfileFactory(owner=django_user_client.user)
    profile2 = ProfileFactory(owner=django_user_client.user)

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


class ClosedFollowsPermissionsBackend(FollowsPermissionsBackend):
    """No new follows are allowed; removing existing ones still is."""

    def has_perm(self, user_obj, perm, obj=None) -> bool | None:
        if perm == "baseapp_follows.add_follow":
            return False
        return super().has_perm(user_obj, perm, obj)


CLOSED_FOLLOWS_BACKENDS = [
    (
        f"{__name__}.ClosedFollowsPermissionsBackend"
        if b == "baseapp_follows.permissions.FollowsPermissionsBackend"
        else b
    )
    for b in settings.AUTHENTICATION_BACKENDS
]


def test_user_can_unfollow_after_add_follow_is_refused(
    django_user_client, graphql_user_client
) -> None:
    actor = ProfileFactory(owner=django_user_client.user)
    target = ProfileFactory()
    follow = FollowFactory(actor_object=actor, target_object=target, user=actor.owner)
    variables = {"input": {"actorObjectId": actor.relay_id, "targetObjectId": target.relay_id}}

    with override_settings(AUTHENTICATION_BACKENDS=CLOSED_FOLLOWS_BACKENDS):
        content = graphql_user_client(FOLLOW_TOGGLE_GRAPHQL, variables=variables).json()

        assert "errors" not in content, content
        assert content["data"]["followToggle"]["actor"]["followingCount"] == 0
        assert not Follow.objects.filter(pk=follow.pk).exists()

        # Following again is refused.
        content = graphql_user_client(FOLLOW_TOGGLE_GRAPHQL, variables=variables).json()

    assert content["errors"][0]["extensions"]["code"] == "permission_required"
    assert Follow.objects.count() == 0
