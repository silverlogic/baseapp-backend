from unittest.mock import patch

import pytest
import swapper
from django.test import override_settings

from baseapp_comments.tests.factories import CommentFactory
from baseapp_profiles.tests.factories import ProfileFactory
from baseapp_reactions.tests.factories import ReactionFactory

Reaction = swapper.load_model("baseapp_reactions", "Reaction")
ReactionTypes = Reaction.ReactionTypes

pytestmark = pytest.mark.django_db

REACTION_TOGGLE_GRAPHQL = """
    mutation ReactionToggleMutation($input: ReactionToggleInput!) {
        reactionToggle(input: $input) {
            reaction {
                node {
                    id
                    reactionType
                }
            }
        }
    }
"""


def test_anon_cant_react(graphql_client):
    comment = CommentFactory()

    response = graphql_client(
        REACTION_TOGGLE_GRAPHQL,
        variables={"input": {"targetObjectId": comment.relay_id, "reactionType": "LIKE"}},
    )
    content = response.json()
    assert content["errors"][0]["message"] == "authentication required"
    assert Reaction.objects.count() == 0


def test_user_can_add_reaction(graphql_user_client):
    comment = CommentFactory()

    with override_settings(BASEAPP_REACTIONS_ENABLE_NOTIFICATIONS=True):
        with patch(
            "baseapp_reactions.notifications.send_reaction_created_notification.delay"
        ) as mock:
            # create reaction with type LIKE
            graphql_user_client(
                REACTION_TOGGLE_GRAPHQL,
                variables={
                    "input": {
                        "targetObjectId": comment.relay_id,
                        "reactionType": ReactionTypes.LIKE.name,
                    }
                },
            )
            assert mock.called
            assert Reaction.objects.count() == 1


def test_user_can_change_reaction(django_user_client, graphql_user_client):
    comment = CommentFactory()
    reaction = ReactionFactory(
        target=comment, user=django_user_client.user, reaction_type=ReactionTypes.LIKE
    )
    # change reaction with type LIKE to DISLIKE
    graphql_user_client(
        REACTION_TOGGLE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": comment.relay_id,
                "reactionType": ReactionTypes.DISLIKE.name,
            }
        },
    )
    comment.refresh_from_db()
    reaction.refresh_from_db()
    assert reaction.reaction_type == ReactionTypes.DISLIKE
    assert comment.reactions_count["total"] == 1
    assert comment.reactions_count["LIKE"] == 0
    assert comment.reactions_count["DISLIKE"] == 1


def test_user_can_remove_reaction(django_user_client, graphql_user_client):
    comment = CommentFactory()

    ReactionFactory(
        target=comment, user=django_user_client.user, reaction_type=ReactionTypes.DISLIKE
    )
    # remove reaction
    graphql_user_client(
        REACTION_TOGGLE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": comment.relay_id,
                "reactionType": ReactionTypes.DISLIKE.name,
            }
        },
    )
    assert Reaction.objects.count() == 0
    comment.refresh_from_db()
    assert comment.reactions_count["total"] == 0
    assert comment.reactions_count["LIKE"] == 0
    assert comment.reactions_count["DISLIKE"] == 0


def test_user_can_react_with_profile(django_user_client, graphql_user_client):
    profile = ProfileFactory(owner=django_user_client.user)
    target = CommentFactory()

    with override_settings(BASEAPP_REACTIONS_ENABLE_NOTIFICATIONS=True):
        with patch(
            "baseapp_reactions.notifications.send_reaction_created_notification.delay"
        ) as mock:
            graphql_user_client(
                REACTION_TOGGLE_GRAPHQL,
                variables={
                    "input": {
                        "targetObjectId": target.relay_id,
                        "reactionType": ReactionTypes.DISLIKE.name,
                        "profileObjectId": profile.relay_id,
                    }
                },
            )
            assert mock.called
    assert Reaction.objects.count() == 1


def test_user_cant_react_with_profile(graphql_user_client):
    profile = ProfileFactory()
    target = CommentFactory()

    response = graphql_user_client(
        REACTION_TOGGLE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": target.relay_id,
                "reactionType": ReactionTypes.DISLIKE.name,
                "profileObjectId": profile.relay_id,
            }
        },
    )
    content = response.json()
    assert content["errors"][0]["extensions"]["code"] == "permission_required"
    assert Reaction.objects.all().count() == 0
