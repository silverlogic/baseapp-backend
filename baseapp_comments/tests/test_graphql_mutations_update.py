import pytest
import swapper
from django.contrib.auth.models import Permission

from baseapp_core.tests.factories import UserFactory

from .factories import CommentFactory

pytestmark = pytest.mark.django_db

Comment = swapper.load_model("baseapp_comments", "Comment")
File = swapper.load_model("baseapp_files", "File")

COMMENT_UPDATE_GRAPHQL = """
    mutation CommentUpdateMutation($input: CommentUpdateInput!) {
        commentUpdate(input: $input) {
            comment {
                id
                body
                files {
                    edges {
                        node {
                            pk
                        }
                    }
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""


def test_anon_cant_update_comment(graphql_client):
    comment = CommentFactory()
    old_body = comment.body

    response = graphql_client(
        COMMENT_UPDATE_GRAPHQL,
        variables={"input": {"id": comment.relay_id, "body": "my edited comment"}},
    )
    content = response.json()
    assert content["errors"][0]["message"] == "authentication required"
    comment.refresh_from_db()
    assert comment.body == old_body


def test_user_cant_update_any_comment(graphql_user_client):
    comment = CommentFactory()
    old_body = comment.body

    response = graphql_user_client(
        COMMENT_UPDATE_GRAPHQL,
        variables={"input": {"id": comment.relay_id, "body": "my edited comment"}},
    )
    content = response.json()
    assert content["errors"][0]["extensions"]["code"] == "permission_required"
    comment.refresh_from_db()
    assert comment.body == old_body


def test_owner_can_update_comment(django_user_client, graphql_user_client):
    comment = CommentFactory(user=django_user_client.user)
    new_body = "my edited comment"

    response = graphql_user_client(
        COMMENT_UPDATE_GRAPHQL,
        variables={"input": {"id": comment.relay_id, "body": new_body}},
    )
    content = response.json()
    assert content["data"]["commentUpdate"]["comment"]["body"] == new_body
    comment.refresh_from_db()
    assert comment.body == new_body


def test_owner_can_attach_files_on_update(django_user_client, graphql_user_client):
    comment = CommentFactory(user=django_user_client.user)
    new_body = "my edited comment with file"
    file = File.objects.create(created_by=django_user_client.user)

    response = graphql_user_client(
        COMMENT_UPDATE_GRAPHQL,
        variables={
            "input": {
                "id": comment.relay_id,
                "body": new_body,
                "fileIds": [file.relay_id],
            }
        },
    )
    content = response.json()
    assert content["data"]["commentUpdate"]["comment"]["body"] == new_body
    assert content["data"]["commentUpdate"]["comment"]["files"]["edges"][0]["node"]["pk"] == file.pk
    comment.refresh_from_db()
    assert comment.body == new_body
    assert comment.files.count() == 1


def test_owner_cannot_attach_foreign_files_on_update(django_user_client, graphql_user_client):
    comment = CommentFactory(user=django_user_client.user)
    other_user = UserFactory()
    foreign_file = File.objects.create(created_by=other_user)

    response = graphql_user_client(
        COMMENT_UPDATE_GRAPHQL,
        variables={
            "input": {
                "id": comment.relay_id,
                "body": comment.body,
                "fileIds": [foreign_file.relay_id],
            }
        },
    )
    content = response.json()

    assert content["errors"][0]["extensions"]["code"] == "permission_required"
    comment.refresh_from_db()
    assert comment.files.count() == 0
    foreign_file.refresh_from_db()
    assert foreign_file.parent is None


def test_user_cant_update_own_comment_if_target_is_disabled(
    django_user_client, graphql_user_client
):
    target = CommentFactory(is_comments_enabled=False)
    comment = CommentFactory(target=target, user=django_user_client.user)
    old_body = comment.body
    new_body = "my edited comment"

    response = graphql_user_client(
        COMMENT_UPDATE_GRAPHQL,
        variables={"input": {"id": comment.relay_id, "body": new_body}},
    )
    content = response.json()
    assert content["errors"][0]["extensions"]["code"] == "permission_required"
    comment.refresh_from_db()
    assert comment.body == old_body


def test_superuser_can_update_comment(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()
    new_body = "my edited comment"

    comment = CommentFactory()

    response = graphql_user_client(
        COMMENT_UPDATE_GRAPHQL,
        variables={"input": {"id": comment.relay_id, "body": new_body}},
    )
    content = response.json()
    assert content["data"]["commentUpdate"]["comment"]["body"] == new_body
    comment.refresh_from_db()
    assert comment.body == new_body


def test_user_with_permission_can_update_comment(django_user_client, graphql_user_client):
    Comment = swapper.load_model("baseapp_comments", "Comment")
    app_label = Comment._meta.app_label
    perm = Permission.objects.get(content_type__app_label=app_label, codename="change_comment")
    django_user_client.user.user_permissions.add(perm)
    new_body = "my edited comment"

    comment = CommentFactory()

    response = graphql_user_client(
        COMMENT_UPDATE_GRAPHQL,
        variables={"input": {"id": comment.relay_id, "body": new_body}},
    )
    content = response.json()
    assert content["data"]["commentUpdate"]["comment"]["body"] == new_body
    comment.refresh_from_db()
    assert comment.body == new_body
