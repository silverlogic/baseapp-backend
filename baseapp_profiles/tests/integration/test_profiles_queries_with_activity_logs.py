import pghistory
import pytest
import swapper

from baseapp.activity_log.models import ActivityLog, VisibilityTypes
from baseapp_comments.tests.factories import CommentFactory

from ..factories import ProfileFactory

pytestmark = pytest.mark.django_db

Comment = swapper.load_model("baseapp_comments", "Comment")

PROFILE_NODE_ACTIVITY_LOGS_QUERY = """
query ProfileNodeActivityLogs($nodeId: ID!) {
  node(id: $nodeId) {
    __typename
    ... on ProfileActivityLogInterface {
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

PROFILE_ROOT_QUERY_WITH_ACTIVITY_LOGS = """
query ProfileWithActivityLogs($id: ID!) {
  profile(id: $id) {
    id
    name
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


def test_profile_node_resolves_activity_logs(graphql_user_client, django_user_client):
    """A Profile node implements ProfileActivityLogInterface and returns matching activity rows."""
    verb = f"{Comment._meta.app_label}.add_comment"
    profile = django_user_client.user.profile

    with pghistory.context(
        user=django_user_client.user.pk,
        profile=profile.pk,
        visibility=VisibilityTypes.PUBLIC,
        verb=verb,
    ):
        CommentFactory()

    response = graphql_user_client(
        PROFILE_NODE_ACTIVITY_LOGS_QUERY,
        variables={"nodeId": profile.relay_id},
    )
    content = response.json()

    assert "errors" not in content, content
    node = content["data"]["node"]
    assert node["__typename"] == "Profile"
    edges = node["activityLogs"]["edges"]
    assert len(edges) == 1

    activity = ActivityLog.objects.get()
    assert edges[0]["node"]["id"] == activity.relay_id
    assert edges[0]["node"]["verb"] == verb
    assert edges[0]["node"]["visibility"] == VisibilityTypes.PUBLIC.name


def test_profile_activity_logs_only_include_own_profile(graphql_user_client, django_user_client):
    """Each profile is scoped to its own activity_logs; other profiles' rows are excluded."""
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    verb = f"{Comment._meta.app_label}.add_comment"
    owner_profile = django_user_client.user.profile
    other_profile = ProfileFactory()

    with pghistory.context(
        user=django_user_client.user.pk,
        profile=owner_profile.pk,
        visibility=VisibilityTypes.PUBLIC,
        verb=verb,
    ):
        CommentFactory()
    with pghistory.context(
        user=django_user_client.user.pk,
        profile=other_profile.pk,
        visibility=VisibilityTypes.PUBLIC,
        verb=verb,
    ):
        CommentFactory()

    assert ActivityLog.objects.count() == 2

    response = graphql_user_client(
        PROFILE_NODE_ACTIVITY_LOGS_QUERY,
        variables={"nodeId": owner_profile.relay_id},
    )
    content = response.json()

    assert "errors" not in content, content
    edges = content["data"]["node"]["activityLogs"]["edges"]
    assert len(edges) == 1


def test_profile_root_query_exposes_activity_logs_field(graphql_user_client, django_user_client):
    """ProfileObjectType surfaces activityLogs from ProfileActivityLogInterface on the profile query."""
    verb = f"{Comment._meta.app_label}.add_comment"
    profile = django_user_client.user.profile

    with pghistory.context(
        user=django_user_client.user.pk,
        profile=profile.pk,
        visibility=VisibilityTypes.PUBLIC,
        verb=verb,
    ):
        CommentFactory()

    response = graphql_user_client(
        PROFILE_ROOT_QUERY_WITH_ACTIVITY_LOGS,
        variables={"id": profile.relay_id},
    )
    content = response.json()

    assert "errors" not in content, content
    data = content["data"]["profile"]
    assert data["id"] == profile.relay_id
    assert data["name"] == profile.name
    assert len(data["activityLogs"]["edges"]) == 1
