import pytest
import swapper

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
    comment = Comment.objects.exclude(pk=target.pk).get()
    target.refresh_from_db()
    assert comment.body == "my comment"
    assert target.comments_count["total"] == 1
    assert target.comments_count["main"] == 1


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
    comment = Comment.objects.filter(in_reply_to=parent).get()
    target.refresh_from_db()
    parent.refresh_from_db()

    assert comment.body == "my reply"

    assert target.comments_count["total"] == 2
    assert target.comments_count["main"] == 1
    assert target.comments_count["replies"] == 1

    assert parent.comments_count["total"] == 1
    assert parent.comments_count["main"] == 1
    assert parent.comments_count["replies"] == 1


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
