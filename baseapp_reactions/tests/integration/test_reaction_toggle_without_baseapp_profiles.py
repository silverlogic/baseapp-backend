from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import swapper

from baseapp_reactions.notifications import send_reaction_created_notification
from baseapp_reactions.permissions import ReactionsPermissionsBackend

pytestmark = pytest.mark.django_db

REACTION_TOGGLE_GRAPHQL = """
mutation ReactionToggleMutation($input: ReactionToggleInput!) {
  reactionToggle(input: $input) {
    reaction {
      node {
        reactionType
      }
    }
  }
}
"""

MY_REACTION_GRAPHQL = """
query MyReaction($id: ID!) {
  node(id: $id) {
    ... on ReactionsInterface {
      myReaction {
        reactionType
      }
    }
  }
}
"""


@pytest.mark.parametrize("with_disabled_apps", [["baseapp_profiles"]], indirect=True)
class TestReactionsWithoutBaseappProfiles:
    def test_mutation_uses_user_based_get_or_create_when_profiles_disabled(
        self, with_disabled_apps, django_user_client, graphql_user_client
    ):
        Reaction = swapper.load_model("baseapp_reactions", "Reaction")
        target = SimpleNamespace(pk=10, is_reactions_enabled=True, refresh_from_db=Mock())
        reaction = Reaction(pk=1, reaction_type=Reaction.ReactionTypes.LIKE)
        fake_content_type = object()

        with (
            patch(
                "baseapp_reactions.graphql.mutations.get_obj_from_relay_id",
                return_value=target,
            ),
            patch(
                "baseapp_reactions.graphql.mutations.ContentType.objects.get_for_model",
                return_value=fake_content_type,
            ),
            patch(
                "baseapp_reactions.graphql.mutations.Reaction.objects.get_or_create",
                return_value=(reaction, True),
            ) as get_or_create,
        ):
            response = graphql_user_client(
                REACTION_TOGGLE_GRAPHQL,
                variables={
                    "input": {
                        "targetObjectId": "target-relay-id",
                        "reactionType": "LIKE",
                    }
                },
            )
            content = response.json()

        assert "errors" not in content
        assert content["data"]["reactionToggle"]["reaction"]["node"]["reactionType"] == "LIKE"
        _, kwargs = get_or_create.call_args
        assert kwargs["user"] == django_user_client.user
        assert kwargs["target_object_id"] == 10
        assert kwargs["target_content_type"] is fake_content_type
        assert kwargs["defaults"] == {"reaction_type": Reaction.ReactionTypes.LIKE}

    def test_mutation_ignores_profile_object_id_when_profiles_disabled(
        self, with_disabled_apps, django_user_client, graphql_user_client
    ):
        Reaction = swapper.load_model("baseapp_reactions", "Reaction")
        target = SimpleNamespace(pk=20, is_reactions_enabled=True, refresh_from_db=Mock())
        reaction = Reaction(pk=2, reaction_type=Reaction.ReactionTypes.LIKE)

        with (
            patch(
                "baseapp_reactions.graphql.mutations.get_obj_from_relay_id",
                return_value=target,
            ) as get_obj_from_relay_id,
            patch(
                "baseapp_reactions.graphql.mutations.ContentType.objects.get_for_model",
                return_value=object(),
            ),
            patch(
                "baseapp_reactions.graphql.mutations.Reaction.objects.get_or_create",
                return_value=(reaction, True),
            ),
        ):
            response = graphql_user_client(
                REACTION_TOGGLE_GRAPHQL,
                variables={
                    "input": {
                        "targetObjectId": "target-relay-id",
                        "reactionType": "LIKE",
                        "profileObjectId": "profile-relay-id",
                    }
                },
            )
            content = response.json()

        assert "errors" not in content
        assert content["data"]["reactionToggle"]["reaction"]["node"]["reactionType"] == "LIKE"
        assert get_obj_from_relay_id.call_count == 1
        assert get_obj_from_relay_id.call_args.args[1] == "target-relay-id"

    def test_my_reaction_resolves_using_current_user_when_profiles_disabled(
        self, with_disabled_apps, django_user_client, graphql_user_client
    ):
        Reaction = swapper.load_model("baseapp_reactions", "Reaction")
        Comment = swapper.load_model("baseapp_comments", "Comment")

        root = Comment(pk=200)
        fake_reaction = Reaction(pk=3, reaction_type=Reaction.ReactionTypes.LIKE)
        fake_content_type = object()
        queryset = Mock()
        queryset.first.return_value = fake_reaction

        with (
            patch(
                "baseapp_core.graphql.relay.Node.get_node_from_global_id",
                return_value=root,
            ),
            patch(
                "baseapp_reactions.graphql.object_types.ContentType.objects.get_for_model",
                return_value=fake_content_type,
            ),
            patch(
                "baseapp_reactions.graphql.object_types.Reaction.objects.filter",
                return_value=queryset,
            ) as reaction_filter,
        ):
            response = graphql_user_client(
                MY_REACTION_GRAPHQL,
                variables={"id": "comment-relay-id"},
            )
            content = response.json()

        assert "errors" not in content
        assert content["data"]["node"]["myReaction"]["reactionType"] == "LIKE"
        reaction_filter.assert_called_once_with(
            target_content_type=fake_content_type,
            target_object_id=200,
            user_id=django_user_client.user.id,
        )

    def test_add_reaction_with_profile_permission_is_disabled_without_profiles(
        self, with_disabled_apps
    ):
        backend = ReactionsPermissionsBackend()
        user = SimpleNamespace(
            is_authenticated=True,
            id=100,
            has_perm=Mock(return_value=True),
        )

        has_perm = backend.has_perm(
            user,
            "baseapp_reactions.add_reaction_with_profile",
            object(),
        )

        assert has_perm is False

    def test_notification_sender_falls_back_to_user_without_profiles(self, with_disabled_apps):
        sender_user = SimpleNamespace(id=12)
        recipient = SimpleNamespace(id=22)
        reaction = SimpleNamespace(profile=None, user=sender_user, target=SimpleNamespace())
        notification_service = Mock()

        with (
            patch(
                "baseapp_reactions.notifications.Reaction.objects.get",
                return_value=reaction,
            ),
            patch(
                "baseapp_reactions.notifications.User.objects.get",
                return_value=recipient,
            ),
            patch(
                "baseapp_core.plugins.shared_services.SharedServiceRegistry.get",
                return_value=notification_service,
            ),
        ):
            send_reaction_created_notification(reaction_pk=1, recipient_id=2)

        assert notification_service.send_notification.called
        assert notification_service.send_notification.call_args.kwargs["sender"] is sender_user
