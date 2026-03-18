from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import swapper

from baseapp_blocks.permissions import BlocksPermissionsBackend

pytestmark = pytest.mark.django_db

BLOCK_TOGGLE_GRAPHQL = """
mutation BlockToggle($input: BlockToggleInput!) {
  blockToggle(input: $input) {
    blockDeletedId
  }
}
"""

IS_BLOCKED_BY_ME_QUERY = """
query IsBlockedByMe($id: ID!) {
  node(id: $id) {
    ... on BlocksInterface {
      isBlockedByMe
    }
  }
}
"""


@pytest.mark.parametrize("with_disabled_apps", [["baseapp_profiles"]], indirect=True)
class TestBlocksWithoutBaseappProfiles:
    def test_mutation_uses_user_based_get_or_create_when_profiles_disabled(
        self, with_disabled_apps, django_user_client, graphql_user_client
    ):
        Block = swapper.load_model("baseapp_blocks", "Block")
        target = SimpleNamespace(pk=10, id=10, refresh_from_db=Mock())
        block = Block(pk=1, user=django_user_client.user)

        with (
            patch(
                "baseapp_blocks.graphql.mutations.get_obj_from_relay_id",
                return_value=target,
            ),
            patch(
                "baseapp_blocks.graphql.mutations.Block.objects.get_or_create",
                return_value=(block, True),
            ) as get_or_create,
        ):
            response = graphql_user_client(
                BLOCK_TOGGLE_GRAPHQL,
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
        Block = swapper.load_model("baseapp_blocks", "Block")
        target = SimpleNamespace(pk=20, id=20, refresh_from_db=Mock())
        block = Block(pk=2)

        with (
            patch(
                "baseapp_blocks.graphql.mutations.get_obj_from_relay_id",
                return_value=target,
            ) as get_obj_from_relay_id,
            patch(
                "baseapp_blocks.graphql.mutations.Block.objects.get_or_create",
                return_value=(block, True),
            ),
        ):
            response = graphql_user_client(
                BLOCK_TOGGLE_GRAPHQL,
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

    def test_is_blocked_by_me_resolves_with_current_user_when_profiles_disabled(
        self, with_disabled_apps, django_user_client, graphql_user_client
    ):
        # GraphQL node resolution requires a model instance of a compatible type.
        # This unsaved Profile instance only satisfies that technical requirement;
        # the behavior under test is the user-based filter branch.
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
                "baseapp_blocks.graphql.object_types.Block.objects.filter",
                return_value=queryset,
            ) as block_filter,
        ):
            response = graphql_user_client(
                IS_BLOCKED_BY_ME_QUERY,
                variables={"id": "target-relay-id"},
            )
            content = response.json()

        assert "errors" not in content
        assert content["data"]["node"]["isBlockedByMe"] is True
        block_filter.assert_called_once_with(
            user_id=django_user_client.user.id,
            target_id=200,
        )

    def test_add_block_with_profile_permission_is_disabled_without_profiles(
        self, with_disabled_apps
    ):
        backend = BlocksPermissionsBackend()
        user = SimpleNamespace(
            is_authenticated=True,
            id=100,
            has_perm=Mock(return_value=True),
        )

        has_perm = backend.has_perm(
            user,
            "baseapp_blocks.add_block_with_profile",
            object(),
        )

        assert has_perm is False
