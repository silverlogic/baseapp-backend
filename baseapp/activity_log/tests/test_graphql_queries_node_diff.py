import pghistory
import pytest
from django.test import override_settings

from baseapp.activity_log.models import VisibilityTypes
from baseapp_comments.tests.factories import CommentFactory

pytestmark = pytest.mark.django_db

ACTIVITY_LOG_DIFFS_GRAPHQL = """
    query ActivityLogDiffs {
        activityLogs {
            edges {
                node {
                    events {
                        edges {
                            node {
                                label
                                diff
                            }
                        }
                    }
                }
            }
        }
    }
"""


def _event_diffs(client) -> list:
    content = client(ACTIVITY_LOG_DIFFS_GRAPHQL).json()
    assert "errors" not in content, content
    return [
        event["node"]["diff"]
        for activity in content["data"]["activityLogs"]["edges"]
        for event in activity["node"]["events"]["edges"]
    ]


def _public_comment_activity(user) -> None:
    comment = CommentFactory(body="before")
    with pghistory.context(user=user.pk, visibility=VisibilityTypes.PUBLIC, verb="comment"):
        comment.body = "the diff holds this body"
        comment.save()


def test_public_activity_diff_is_visible_by_default(
    django_user_client, graphql_user_client
) -> None:
    _public_comment_activity(django_user_client.user)

    diffs = _event_diffs(graphql_user_client)

    assert diffs
    assert any(diff and "the diff holds this body" in str(diff) for diff in diffs)


@override_settings(BASEAPP_ACTIVITY_LOG_PUBLIC_NODE_DIFF=False)
def test_public_activity_diff_is_hidden_when_not_public(
    django_user_client, graphql_user_client
) -> None:
    _public_comment_activity(django_user_client.user)

    diffs = _event_diffs(graphql_user_client)

    assert diffs
    assert all(diff is None for diff in diffs)


@override_settings(BASEAPP_ACTIVITY_LOG_PUBLIC_NODE_DIFF=False)
def test_superuser_sees_the_diff_when_not_public(django_user_client, graphql_user_client) -> None:
    django_user_client.user.is_superuser = True
    django_user_client.user.save()
    _public_comment_activity(django_user_client.user)

    diffs = _event_diffs(graphql_user_client)

    assert any(diff and "the diff holds this body" in str(diff) for diff in diffs)
