import pytest
import swapper
from django.contrib.auth.models import Permission
from django.test import override_settings

from .factories import CommentFactory

pytestmark = pytest.mark.django_db

COMMENT_PIN_GRAPHQL = """
    mutation CommentPinMutation($input: CommentPinInput!) {
        commentPin(input: $input) {
            comment {
                id
                isPinned
            }
            errors {
                field
                messages
            }
        }
    }
"""


def test_user_cant_pin_own_comment(django_user_client, graphql_user_client):
    target = CommentFactory()
    comment = CommentFactory(target=target, user=django_user_client.user)

    response = graphql_user_client(
        COMMENT_PIN_GRAPHQL,
        variables={"input": {"id": comment.relay_id}},
    )
    content = response.json()
    assert content["errors"][0]["extensions"]["code"] == "permission_required"
    comment.refresh_from_db()
    assert comment.is_pinned is False


def test_user_cant_pin_others_comment(graphql_user_client):
    target = CommentFactory()
    comment = CommentFactory(target=target)

    response = graphql_user_client(
        COMMENT_PIN_GRAPHQL,
        variables={"input": {"id": comment.relay_id}},
    )
    content = response.json()
    assert content["errors"][0]["extensions"]["code"] == "permission_required"
    comment.refresh_from_db()
    assert comment.is_pinned is False


def test_superuser_can_pin_comment(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    target = CommentFactory()
    comment = CommentFactory(target=target)

    response = graphql_user_client(
        COMMENT_PIN_GRAPHQL,
        variables={"input": {"id": comment.relay_id}},
    )
    content = response.json()
    comment.refresh_from_db()
    target.refresh_from_db()
    assert content["data"]["commentPin"]["comment"]["isPinned"] is True
    assert target.comments_count["pinned"] == 1
    assert comment.is_pinned is True


def test_user_with_permission_can_pin_comment(django_user_client, graphql_user_client):
    Comment = swapper.load_model("baseapp_comments", "Comment")
    app_label = Comment._meta.app_label
    perm = Permission.objects.get(content_type__app_label=app_label, codename="pin_comment")
    django_user_client.user.user_permissions.add(perm)

    target = CommentFactory()
    comment = CommentFactory(target=target)

    response = graphql_user_client(
        COMMENT_PIN_GRAPHQL,
        variables={"input": {"id": comment.relay_id}},
    )
    content = response.json()
    comment.refresh_from_db()
    assert content["data"]["commentPin"]["comment"]["isPinned"] is True
    assert comment.is_pinned is True
    assert comment.is_pinned is True


@override_settings(BASEAPP_COMMENTS_MAX_PINS_PER_THREAD=1)
def test_cant_pin_more_than_maximum_per_main_thread(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    target = CommentFactory()
    CommentFactory(target=target, is_pinned=True)
    comment = CommentFactory(target=target)

    response = graphql_user_client(
        COMMENT_PIN_GRAPHQL,
        variables={"input": {"id": comment.relay_id}},
    )
    content = response.json()

    assert content["errors"][0]["extensions"]["code"] == "max_pins_reached"
    comment.refresh_from_db()
    assert comment.is_pinned is False


@override_settings(BASEAPP_COMMENTS_MAX_PINS_PER_THREAD=1)
def test_cant_pin_more_than_maximum_per_reply_thread(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    target = CommentFactory()
    parent = CommentFactory(target=target)
    CommentFactory(target=target, in_reply_to=parent, is_pinned=True)
    comment = CommentFactory(target=target, in_reply_to=parent)

    response = graphql_user_client(
        COMMENT_PIN_GRAPHQL,
        variables={"input": {"id": comment.relay_id}},
    )
    content = response.json()

    assert content["errors"][0]["extensions"]["code"] == "max_pins_reached"
    comment.refresh_from_db()
    assert comment.is_pinned is False
