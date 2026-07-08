import pghistory
import pytest
import swapper
from django.contrib.auth import get_user_model

from baseapp.activity_log.models import ActivityLog, VisibilityTypes
from baseapp_comments.tests.factories import CommentFactory
from baseapp_core.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

Comment = swapper.load_model("baseapp_comments", "Comment")
User = get_user_model()

USER_NODE_ACTIVITY_LOGS_QUERY = """
query UserNodeActivityLogs($nodeId: ID!) {
  node(id: $nodeId) {
    __typename
    ... on UserActivityLogInterface {
      activityLogs(first: 10) {
        edges {
          node {
            id
            verb
            visibility
          }
        }
      }
    }
  }
}
"""

USER_ROOT_QUERY_WITH_ACTIVITY_LOGS = """
query UserWithActivityLogs($id: ID!) {
  user(id: $id) {
    id
    isAuthenticated
    activityLogs(first: 10) {
      edges {
        node {
          id
          verb
        }
      }
    }
  }
}
"""


def test_user_node_resolves_activity_logs(graphql_user_client, django_user_client):
    """A User node implements UserActivityLogInterface and returns matching activity rows."""
    verb = f"{Comment._meta.app_label}.add_comment"
    user = django_user_client.user

    with pghistory.context(
        user=user.pk,
        visibility=VisibilityTypes.PUBLIC,
        verb=verb,
    ):
        CommentFactory()

    response = graphql_user_client(
        USER_NODE_ACTIVITY_LOGS_QUERY,
        variables={"nodeId": user.relay_id},
    )
    content = response.json()

    assert "errors" not in content, content
    node = content["data"]["node"]
    assert node["__typename"] == "User"
    edges = node["activityLogs"]["edges"]
    assert len(edges) == 1

    activity = ActivityLog.objects.get()
    assert edges[0]["node"]["id"] == activity.relay_id
    assert edges[0]["node"]["verb"] == verb
    assert edges[0]["node"]["visibility"] == VisibilityTypes.PUBLIC.name


def test_user_activity_logs_only_include_own_user(graphql_user_client, django_user_client):
    """Each user is scoped to their own activity_logs; other users' rows are excluded."""
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    verb = f"{Comment._meta.app_label}.add_comment"
    owner = django_user_client.user
    other = UserFactory()

    with pghistory.context(
        user=owner.pk,
        visibility=VisibilityTypes.PUBLIC,
        verb=verb,
    ):
        CommentFactory()
    with pghistory.context(
        user=other.pk,
        visibility=VisibilityTypes.PUBLIC,
        verb=verb,
    ):
        CommentFactory()

    assert ActivityLog.objects.count() == 2

    response = graphql_user_client(
        USER_NODE_ACTIVITY_LOGS_QUERY,
        variables={"nodeId": owner.relay_id},
    )
    content = response.json()

    assert "errors" not in content, content
    edges = content["data"]["node"]["activityLogs"]["edges"]
    assert len(edges) == 1


def test_user_root_query_exposes_activity_logs_field(graphql_user_client, django_user_client):
    """UserObjectType surfaces activityLogs from UserActivityLogInterface on the user query."""
    verb = f"{Comment._meta.app_label}.add_comment"
    user = django_user_client.user

    with pghistory.context(
        user=user.pk,
        visibility=VisibilityTypes.PUBLIC,
        verb=verb,
    ):
        CommentFactory()

    response = graphql_user_client(
        USER_ROOT_QUERY_WITH_ACTIVITY_LOGS,
        variables={"id": user.relay_id},
    )
    content = response.json()

    assert "errors" not in content, content
    data = content["data"]["user"]
    assert data["id"] == user.relay_id
    assert data["isAuthenticated"] is True
    assert len(data["activityLogs"]["edges"]) == 1
