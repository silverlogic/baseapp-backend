import pytest

from baseapp_comments.tests.factories import CommentFactory

from .factories import ReactionFactory

pytestmark = pytest.mark.django_db

VIEW_QUERY = """
    query GetObject($id: ID!) {
        node(id: $id) {
            ... on ReactionsInterface {
                reactionsCount {
                    total
                }
                reactions {
                    edges {
                        node {
                            id
                            pk
                        }
                    }
                }
            }
        }
    }
"""


def test_user_can_see_reactions(django_user_client, graphql_user_client):
    comment = CommentFactory(user=django_user_client.user)
    ReactionFactory(target=comment)
    response = graphql_user_client(VIEW_QUERY, variables={"id": comment.relay_id})
    content = response.json()
    assert content["data"]["node"]["reactionsCount"]["total"] == 1
    assert len(content["data"]["node"]["reactions"]["edges"]) == 1


# def test_user_can_see_reactions(django_user_instructor, graphql_user_instructor):
#     user = django_user_instructor.user
#     classroom = django_user_instructor.member.classroom
#     comment = ClassroomCommentFactory(target=classroom, user=user)
#     CommentReactionFactory(target=comment)
#     response = graphql_user_instructor(
#         "query { allClassrooms { totalCount edges { node { id commentsCount comments { edges { node { id content reactionsCount { total }}}} } } } }"
#     )
#     content = response.json()
#     assert content["data"]["allClassrooms"]["totalCount"] == 1
#     assert len(content["data"]["allClassrooms"]["edges"]) == 1
#     assert (
#         content["data"]["allClassrooms"]["edges"][0]["node"]["comments"]["edges"][0]["node"][
#             "reactionsCount"
#         ]["total"]
#         == 1
#     )
