import pghistory
import pytest

from baseapp.activity_log.models import ActivityLog, VisibilityTypes
from baseapp_comments.tests.factories import CommentFactory
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

ACTIVITY_LOGS_QUERY = """
    query {
        activityLogs {
            totalCount
            edges {
                node {
                    id
                    verb
                    user { id }
                    profile { id }
                    events { totalCount edges { node { label createdAt data diff } } }
                }
            }
        }
    }
"""


def test_activity_logs_without_user_or_profile_are_listed(
    django_user_client, graphql_user_client
) -> None:
    django_user_client.user.is_superuser = True
    django_user_client.user.save()
    profile = ProfileFactory()
    with pghistory.context(profile=profile.pk, visibility=VisibilityTypes.PUBLIC, verb="a"):
        CommentFactory()
    with pghistory.context(
        user=django_user_client.user.pk, visibility=VisibilityTypes.PRIVATE, verb="b"
    ):
        CommentFactory()

    content = graphql_user_client(ACTIVITY_LOGS_QUERY).json()

    assert "errors" not in content
    nodes = {e["node"]["verb"]: e["node"] for e in content["data"]["activityLogs"]["edges"]}
    assert content["data"]["activityLogs"]["totalCount"] == 2
    assert nodes["a"]["user"] is None
    assert nodes["a"]["profile"] == {"id": profile.relay_id}
    assert nodes["b"]["user"] == {"id": django_user_client.user.relay_id}
    assert nodes["b"]["profile"] is None
    assert nodes["a"]["events"]["totalCount"] >= 1
    assert nodes["a"]["events"]["edges"][0]["node"]["data"] is not None


def test_activity_log_node_skips_visibility_filter(django_user_client, graphql_user_client) -> None:
    with pghistory.context(
        user=django_user_client.user.pk, visibility=VisibilityTypes.PRIVATE, verb="b"
    ):
        CommentFactory()
    activity = ActivityLog.objects.get()
    query = "query ($id: ID!) { node(id: $id) { ... on ActivityLog { verb } } }"

    content = graphql_user_client(query, variables={"id": activity.relay_id}).json()

    assert content["data"]["node"] == {"verb": "b"}


def test_activity_logs_first_is_capped(graphql_user_client) -> None:
    content = graphql_user_client("query { activityLogs(first: 101) { totalCount } }").json()

    assert "errors" in content
