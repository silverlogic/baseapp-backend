import pytest
import swapper
from django.conf import settings
from django.contrib.auth.models import Permission
from django.test import override_settings

from baseapp.activity_log.models import ActivityLog, VisibilityTypes
from baseapp_comments.permissions import CommentsPermissionsBackend
from baseapp_pages.tests.factories import PageFactory

from ..factories import CommentFactory

pytestmark = [pytest.mark.django_db, pytest.mark.celery_app]

Comment = swapper.load_model("baseapp_comments", "Comment")
Page = swapper.load_model("baseapp_pages", "Page")
app_label = Comment._meta.app_label


class PrivatePageCommentActivityBackend(CommentsPermissionsBackend):
    """Comment activity on pages stays private; every other target keeps the defaults."""

    def has_perm(self, user_obj, perm, obj=None) -> bool | None:
        if perm == f"{app_label}.publish_comment_activity" and isinstance(obj, Page):
            return False
        return super().has_perm(user_obj, perm, obj)


private_page_comment_activity = override_settings(
    AUTHENTICATION_BACKENDS=[
        (
            "baseapp_comments.tests.integration.test_comment_activity_visibility."
            "PrivatePageCommentActivityBackend"
            if backend == "baseapp_comments.permissions.CommentsPermissionsBackend"
            else backend
        )
        for backend in settings.AUTHENTICATION_BACKENDS
    ]
)

COMMENT_CREATE_GRAPHQL = """
    mutation CommentCreate($input: CommentCreateInput!) {
        commentCreate(input: $input) {
            comment { node { id } }
        }
    }
"""

COMMENT_UPDATE_GRAPHQL = """
    mutation CommentUpdate($input: CommentUpdateInput!) {
        commentUpdate(input: $input) {
            comment { id }
        }
    }
"""

COMMENT_PIN_GRAPHQL = """
    mutation CommentPin($input: CommentPinInput!) {
        commentPin(input: $input) {
            comment { id }
        }
    }
"""

ACTIVITY_LOGS_GRAPHQL = """
    query ActivityLogs {
        activityLogs {
            edges { node { verb } }
        }
    }
"""


def _public_verbs() -> list[str]:
    return list(
        ActivityLog.objects.filter(visibility=VisibilityTypes.PUBLIC).values_list("verb", flat=True)
    )


def test_comment_activity_is_public_by_default(graphql_user_client, celery_config) -> None:
    page = PageFactory()

    graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={"input": {"targetObjectId": page.relay_id, "body": "my comment"}},
    )

    assert _public_verbs() == [f"{app_label}.add_comment"]


@private_page_comment_activity
def test_comment_create_activity_stays_private_when_denied(
    graphql_user_client, graphql_client, celery_config
) -> None:
    page = PageFactory()

    graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={"input": {"targetObjectId": page.relay_id, "body": "internal note"}},
    )

    assert Comment.objects.filter(body="internal note").exists()
    assert _public_verbs() == []
    content = graphql_client(ACTIVITY_LOGS_GRAPHQL).json()
    assert content["data"]["activityLogs"]["edges"] == []


@private_page_comment_activity
def test_comment_activity_on_other_targets_stays_public(graphql_user_client, celery_config) -> None:
    target = CommentFactory()

    graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={"input": {"targetObjectId": target.relay_id, "body": "my comment"}},
    )

    assert _public_verbs() == [f"{app_label}.add_comment"]


@private_page_comment_activity
def test_comment_update_activity_stays_private_when_denied(
    django_user_client, graphql_user_client, celery_config
) -> None:
    comment = CommentFactory(target=PageFactory(), user=django_user_client.user)

    graphql_user_client(
        COMMENT_UPDATE_GRAPHQL,
        variables={"input": {"id": comment.relay_id, "body": "edited note"}},
    )

    comment.refresh_from_db()
    assert comment.body == "edited note"
    assert _public_verbs() == []


@private_page_comment_activity
def test_comment_pin_activity_stays_private_when_denied(
    django_user_client, graphql_user_client, celery_config
) -> None:
    perm = Permission.objects.get(content_type__app_label=app_label, codename="pin_comment")
    django_user_client.user.user_permissions.add(perm)
    comment = CommentFactory(target=PageFactory())

    graphql_user_client(COMMENT_PIN_GRAPHQL, variables={"input": {"id": comment.relay_id}})

    comment.refresh_from_db()
    assert comment.is_pinned is True
    assert _public_verbs() == []


def test_refused_comment_create_sets_no_public_activity(graphql_user_client, celery_config) -> None:
    target = CommentFactory(is_comments_enabled=False)

    content = graphql_user_client(
        COMMENT_CREATE_GRAPHQL,
        variables={"input": {"targetObjectId": target.relay_id, "body": "refused"}},
    ).json()

    assert content["errors"][0]["extensions"]["code"] == "permission_required"
    assert _public_verbs() == []
