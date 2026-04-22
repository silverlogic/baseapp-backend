import pytest
import swapper

from baseapp_core.plugins import shared_services
from baseapp_profiles.tests.factories import ProfileFactory

from .factories import CommentFactory

pytestmark = pytest.mark.django_db

Comment = swapper.load_model("baseapp_comments", "Comment")

COMMENT_CREATE_GRAPHQL = """
    mutation CommentCreateMutation($input: CommentCreateInput!) {
        commentCreate(input: $input) {
            comment {
                node {
                    id
                    body
                }
            }
            errors {
                field
                messages
            }
            _debug {
                exceptions {
                    stack
                }
            }
        }
    }
"""


def test_anon_cant_comment(graphql_client):
    target = CommentFactory()

    response = graphql_client(
        COMMENT_CREATE_GRAPHQL,
        variables={"input": {"targetObjectId": target.relay_id, "body": "my comment"}},
    )
    content = response.json()
    assert content["errors"][0]["message"] == "authentication required"
    assert Comment.objects.exclude(pk=target.pk).count() == 0


def test_user_can_comment(graphql_user_client):
    target = CommentFactory()

    graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={"input": {"targetObjectId": target.relay_id, "body": "my comment"}},
    )
    service = shared_services.get("commentable_metadata")
    comment = Comment.objects.exclude(pk=target.pk).get()
    assert comment.body == "my comment"
    assert service.get_comments_count(target)["total"] == 1
    assert service.get_comments_count(target)["main"] == 1


def test_user_cant_comment_if_disabled(graphql_user_client):
    target = CommentFactory(is_comments_enabled=False)

    response = graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={"input": {"targetObjectId": target.relay_id, "body": "my comment"}},
    )
    content = response.json()
    assert content["errors"][0]["extensions"]["code"] == "permission_required"
    assert Comment.objects.exclude(pk=target.pk).count() == 0


def test_user_can_reply(graphql_user_client):
    target = CommentFactory()
    parent = CommentFactory(target=target)

    graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": target.relay_id,
                "body": "my reply",
                "inReplyToId": parent.relay_id,
            }
        },
    )
    service = shared_services.get("commentable_metadata")
    comment = Comment.objects.filter(in_reply_to=parent).get()

    assert comment.body == "my reply"

    assert service.get_comments_count(target)["total"] == 2
    assert service.get_comments_count(target)["main"] == 1
    assert service.get_comments_count(target)["replies"] == 1

    assert service.get_comments_count(parent)["total"] == 1
    assert service.get_comments_count(parent)["main"] == 1
    assert service.get_comments_count(parent)["replies"] == 1


def test_user_can_comment_with_profile(django_user_client, graphql_user_client):
    profile = ProfileFactory(owner=django_user_client.user)
    target = CommentFactory()

    graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": target.relay_id,
                "body": "my comment",
                "profileId": profile.relay_id,
            }
        },
    )
    assert Comment.objects.exclude(pk=target.pk).count() == 1


def test_user_cant_comment_with_profile(graphql_user_client):
    profile = ProfileFactory()
    target = CommentFactory()

    response = graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={
            "input": {
                "targetObjectId": target.relay_id,
                "body": "my comment",
                "profileId": profile.relay_id,
            }
        },
    )
    content = response.json()
    assert content["errors"][0]["extensions"]["code"] == "permission_required"
    assert Comment.objects.exclude(pk=target.pk).count() == 0
