from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import swapper

from baseapp_follows.permissions import FollowsPermissionsBackend

pytestmark = pytest.mark.django_db

FOLLOW_TOGGLE_GRAPHQL = """
mutation FollowToggle($input: FollowToggleInput!) {
  followToggle(input: $input) {
    followDeletedId
  }
}
"""

IS_FOLLOWED_BY_ME_QUERY = """
query IsFollowedByMe($id: ID!) {
  node(id: $id) {
    ... on FollowsInterface {
      isFollowedByMe
    }
  }
}
"""


@pytest.mark.parametrize("with_disabled_apps", [["baseapp_profiles"]], indirect=True)
class TestFollowsWithoutBaseappProfiles:
    def test_mutation_uses_user_based_get_or_create_when_profiles_disabled(
        self, with_disabled_apps, django_user_client, graphql_user_client
    ):
        Follow = swapper.load_model("baseapp_follows", "Follow")
        target = SimpleNamespace(pk=10, refresh_from_db=Mock())
        follow = Follow(pk=1, user=django_user_client.user, target_is_following_back=False)

        with (
            patch(
                "baseapp_follows.graphql.mutations.get_obj_from_relay_id",
                return_value=target,
            ),
            patch(
                "baseapp_follows.graphql.mutations.Follow.objects.get_or_create",
                return_value=(follow, True),
            ) as get_or_create,
        ):
            response = graphql_user_client(
                FOLLOW_TOGGLE_GRAPHQL,
                variables={
                    "input": {
                        "actorObjectId": "actor-relay-id",
                        "targetObjectId": "target-relay-id",
                    }
                },
            )
            content = response.json()

        assert "errors" not in content
        _, kwargs = get_or_create.call_args
        assert kwargs["target"] is target
        assert kwargs["user"] == django_user_client.user
        assert "actor" not in kwargs

    def test_mutation_ignores_actor_object_id_when_profiles_disabled(
        self, with_disabled_apps, graphql_user_client
    ):
        Follow = swapper.load_model("baseapp_follows", "Follow")
        target = SimpleNamespace(pk=20, refresh_from_db=Mock())
        follow = Follow(pk=2, target_is_following_back=False)

        with (
            patch(
                "baseapp_follows.graphql.mutations.get_obj_from_relay_id",
                return_value=target,
            ) as get_obj_from_relay_id,
            patch(
                "baseapp_follows.graphql.mutations.Follow.objects.get_or_create",
                return_value=(follow, True),
            ),
        ):
            response = graphql_user_client(
                FOLLOW_TOGGLE_GRAPHQL,
                variables={
                    "input": {
                        "actorObjectId": "actor-relay-id",
                        "targetObjectId": "target-relay-id",
                    }
                },
            )
            content = response.json()

        assert "errors" not in content
        assert get_obj_from_relay_id.call_count == 1
        assert get_obj_from_relay_id.call_args.args[1] == "target-relay-id"

    def test_is_followed_by_me_resolves_with_current_user_when_profiles_disabled(
        self, with_disabled_apps, django_user_client, graphql_user_client
    ):
        # Node resolution expects a model instance compatible with GraphQL type resolution.
        # This unsaved Profile only satisfies that technical requirement; the behavior under
        # test is still the "without profiles" branch that filters by current user id.
        Profile = swapper.load_model("baseapp_profiles", "Profile")
        root = Profile(pk=200)
        queryset = Mock()
        queryset.exists.return_value = True

        with (
            patch(
                "baseapp_core.graphql.relay.Node.get_node_from_global_id",
                return_value=root,
            ),
            patch(
                "baseapp_follows.graphql.interfaces.Follow.objects.filter",
                return_value=queryset,
            ) as follow_filter,
        ):
            response = graphql_user_client(
                IS_FOLLOWED_BY_ME_QUERY,
                variables={"id": "target-relay-id"},
            )
            content = response.json()

        assert "errors" not in content
        assert content["data"]["node"]["isFollowedByMe"] is True
        follow_filter.assert_called_once_with(
            user_id=django_user_client.user.id,
            target_id=200,
        )

    def test_add_follow_with_profile_permission_is_disabled_without_profiles(
        self, with_disabled_apps
    ):
        backend = FollowsPermissionsBackend()
        user = SimpleNamespace(
            is_authenticated=True,
            id=100,
            has_perm=Mock(return_value=True),
        )

        has_perm = backend.has_perm(
            user,
            "baseapp_follows.add_follow_with_profile",
            object(),
        )

        assert has_perm is False
