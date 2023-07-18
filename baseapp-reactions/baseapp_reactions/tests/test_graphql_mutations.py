import baseapp_comments.tests.factories as f
import pytest
import swapper
from baseapp_comments.graphql.object_types import CommentNode
from graphql_relay import to_global_id

from ..models import ReactionTypes

Reaction = swapper.load_model("baseapp_reactions", "Reaction")

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
    comment = f.ClassroomCommentFactory()

    # TO DO: make to_global_id easier get, maybe like obj.relay_id
    comment_relay_id = to_global_id(CommentNode._meta.name, comment.pk)
    response = graphql_client(
        REACTION_TOGGLE_GRAPHQL,
        variables={"input": {"targetObjectId": comment_relay_id, "type": "LIKE"}},
    )
    content = response.json()
    assert content["errors"][0]["message"] == "authentication required"
    assert Reaction.objects.count() == 0


def test_user_can_react(graphql_user_client):
    comment = f.ClassroomCommentFactory()

    # TO DO: make to_global_id easier get, maybe like obj.relay_id
    comment_relay_id = to_global_id(CommentNode._meta.name, comment.pk)

    # create reaction with type LIKE
    graphql_user_client(
        REACTION_TOGGLE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": comment_relay_id,
                "type": ReactionTypes.LIKE.name,
            }
        },
    )
    assert Reaction.objects.count() == 1

    # change reaction with type LIKE to GRR
    graphql_user_client(
        REACTION_TOGGLE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": comment_relay_id,
                "type": ReactionTypes.GRR.name,
            }
        },
    )
    assert Reaction.objects.count() == 1
    assert Reaction.objects.filter(type=ReactionTypes.GRR).count() == 1

    # remove reaction
    graphql_user_client(
        REACTION_TOGGLE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": comment_relay_id,
                "type": ReactionTypes.GRR.name,
            }
        },
    )
    assert Reaction.objects.count() == 0
