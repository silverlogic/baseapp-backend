import pytest
import swapper
from django.contrib.auth.models import Permission

from .factories import CommentFactory

pytestmark = pytest.mark.django_db

Comment = swapper.load_model("baseapp_comments", "Comment")


COMMENT_DELETE_GRAPHQL = """
    mutation CommentDeleteMutation($input: CommentDeleteInput!) {
        commentDelete(input: $input) {
            deletedId
            inReplyTo {
                id
                commentsCount {
                    total
                    replies
                }
            }
            target {
                id
                commentsCount {
                    total
                    replies
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""


def test_anon_cant_delete_comment(graphql_client):
    comment = CommentFactory()

    response = graphql_client(
        COMMENT_DELETE_GRAPHQL,
        variables={"input": {"id": comment.relay_id}},
    )
    content = response.json()
    assert content["errors"][0]["message"] == "authentication required"
    assert Comment.objects_visible.count() == 1


def test_user_cant_delete_any_comment(graphql_user_client):
    comment = CommentFactory()

    response = graphql_user_client(
        COMMENT_DELETE_GRAPHQL,
        variables={"input": {"id": comment.relay_id}},
    )
    content = response.json()
    assert content["errors"][0]["extensions"]["code"] == "permission_required"
    assert Comment.objects_visible.count() == 1


def test_owner_can_delete_comment(django_user_client, graphql_user_client):
    comment = CommentFactory(user=django_user_client.user)

    response = graphql_user_client(
        COMMENT_DELETE_GRAPHQL,
        variables={"input": {"id": comment.relay_id}},
    )
    content = response.json()
    assert content["data"]["commentDelete"]["deletedId"] == comment.relay_id
    assert Comment.objects_visible.count() == 0


def test_superuser_can_delete_comment(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    comment = CommentFactory()

    response = graphql_user_client(
        COMMENT_DELETE_GRAPHQL,
        variables={"input": {"id": comment.relay_id}},
    )
    content = response.json()
    assert content["data"]["commentDelete"]["deletedId"] == comment.relay_id
    assert Comment.objects_visible.count() == 0


def test_user_with_permission_can_delete_comment(django_user_client, graphql_user_client):
    app_label = Comment._meta.app_label
    perm = Permission.objects.get(content_type__app_label=app_label, codename="delete_comment")
    django_user_client.user.user_permissions.add(perm)

    comment = CommentFactory()

    response = graphql_user_client(
        COMMENT_DELETE_GRAPHQL,
        variables={"input": {"id": comment.relay_id}},
    )
    content = response.json()
    assert content["data"]["commentDelete"]["deletedId"] == comment.relay_id
    assert Comment.objects_visible.count() == 0


def test_update_comments_counts_after_delete_comment(django_user_client, graphql_user_client):
    target = CommentFactory()
    parent = CommentFactory(target=target)

    comment = CommentFactory(user=django_user_client.user, target=target, in_reply_to=parent)

    assert target.comments_count["total"] == 2
    assert target.comments_count["replies"] == 1

    assert parent.comments_count["total"] == 1

    response = graphql_user_client(
        COMMENT_DELETE_GRAPHQL,
        variables={"input": {"id": comment.relay_id}},
    )
    content = response.json()

    assert content["data"]["commentDelete"]["target"]["commentsCount"]["total"] == 1
    assert content["data"]["commentDelete"]["target"]["commentsCount"]["replies"] == 0
    assert content["data"]["commentDelete"]["inReplyTo"]["commentsCount"]["total"] == 0

    target.refresh_from_db()
    parent.refresh_from_db()

    assert target.comments_count["total"] == 1
    assert target.comments_count["replies"] == 0

    assert parent.comments_count["total"] == 0
