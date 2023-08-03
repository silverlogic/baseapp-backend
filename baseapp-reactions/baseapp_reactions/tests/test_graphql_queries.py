import pytest
from baseapp_comments.tests.factories import ClassroomCommentFactory

from .factories import CommentReactionFactory

pytestmark = pytest.mark.django_db


def test_student_can_see_reactions(django_user_student, graphql_user_student):
    user = django_user_student.user
    classroom = django_user_student.member.classroom
    comment = ClassroomCommentFactory(target=classroom, user=user)
    CommentReactionFactory(target=comment)
    response = graphql_user_student(
        "query { allClassrooms { totalCount edges { node { id commentsCount comments { edges { node { id content reactionsCount { total }}}} } } } }"
    )
    content = response.json()
    assert content["data"]["allClassrooms"]["totalCount"] == 1
    assert len(content["data"]["allClassrooms"]["edges"]) == 1
    assert (
        content["data"]["allClassrooms"]["edges"][0]["node"]["comments"]["edges"][0]["node"][
            "reactionsCount"
        ]["total"]
        == 1
    )


def test_instructor_can_see_reactions(django_user_instructor, graphql_user_instructor):
    user = django_user_instructor.user
    classroom = django_user_instructor.member.classroom
    comment = ClassroomCommentFactory(target=classroom, user=user)
    CommentReactionFactory(target=comment)
    response = graphql_user_instructor(
        "query { allClassrooms { totalCount edges { node { id commentsCount comments { edges { node { id content reactionsCount { total }}}} } } } }"
    )
    content = response.json()
    assert content["data"]["allClassrooms"]["totalCount"] == 1
    assert len(content["data"]["allClassrooms"]["edges"]) == 1
    assert (
        content["data"]["allClassrooms"]["edges"][0]["node"]["comments"]["edges"][0]["node"][
            "reactionsCount"
        ]["total"]
        == 1
    )
