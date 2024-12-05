import pytest
import swapper
from django.contrib.auth.models import Permission

from .factories import CommentFactory

pytestmark = pytest.mark.django_db

VIEW_ALL_QUERY = """
    query {
        allComments {
            totalCount
            edges {
                node {
                    id
                    body
                    commentsCount {
                        main
                    }
                    comments {
                        edges {
                            node {
                                id
                                body
                            }
                        }
                    }
                }
            }
        }
    }
"""


def test_anon_see_nothing(graphql_client):
    CommentFactory()
    response = graphql_client(VIEW_ALL_QUERY)
    content = response.json()
    assert content["data"]["allComments"]["totalCount"] == 0
    assert len(content["data"]["allComments"]["edges"]) == 0


def test_user_see_nothing(graphql_user_client):
    CommentFactory()
    response = graphql_user_client(VIEW_ALL_QUERY)
    content = response.json()
    assert content["data"]["allComments"]["totalCount"] == 0
    assert len(content["data"]["allComments"]["edges"]) == 0


def test_superuser_can_list(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    comment = CommentFactory()
    response = graphql_user_client(VIEW_ALL_QUERY)
    content = response.json()

    assert content["data"]["allComments"]["totalCount"] == 1
    assert len(content["data"]["allComments"]["edges"]) == 1
    assert content["data"]["allComments"]["edges"][0]["node"]["body"] == comment.body


def test_user_with_permission_can_list(django_user_client, graphql_user_client):
    Comment = swapper.load_model("baseapp_comments", "Comment")
    app_label = Comment._meta.app_label
    perm = Permission.objects.get(content_type__app_label=app_label, codename="view_all_comments")
    django_user_client.user.user_permissions.add(perm)

    comment = CommentFactory()
    response = graphql_user_client(VIEW_ALL_QUERY)
    content = response.json()

    assert content["data"]["allComments"]["totalCount"] == 1
    assert len(content["data"]["allComments"]["edges"]) == 1
    assert content["data"]["allComments"]["edges"][0]["node"]["body"] == comment.body
