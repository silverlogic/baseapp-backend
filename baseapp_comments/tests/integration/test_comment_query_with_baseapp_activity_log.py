import pghistory
import pytest
import swapper

from baseapp.activity_log.models import ActivityLog, VisibilityTypes

from ..factories import CommentFactory

pytestmark = pytest.mark.django_db

Comment = swapper.load_model("baseapp_comments", "Comment")

COMMENT_NODE_ACTIVITY_LOGS_QUERY = """
query CommentNodeActivityLogs($nodeId: ID!) {
  node(id: $nodeId) {
    __typename
    ... on NodeActivityLogInterface {
      nodeActivityLogs(first: 10) {
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


COMMENT_WITH_BODY_AND_ACTIVITY_LOGS_QUERY = """
query CommentWithActivityLogs($nodeId: ID!) {
  node(id: $nodeId) {
    ... on Comment {
      body
      nodeActivityLogs(first: 10) {
        edges {
          node {
            id
            verb
          }
        }
      }
    }
  }
}
"""


def test_comment_node_resolves_node_activity_logs(graphql_user_client, django_user_client):
    """A Comment node implements NodeActivityLogInterface and returns its pghistory context."""
    verb = f"{Comment._meta.app_label}.add_comment"
    with pghistory.context(
        user=django_user_client.user.pk,
        visibility=VisibilityTypes.PUBLIC,
        verb=verb,
    ):
        comment = CommentFactory(body="activity log wiring")

    response = graphql_user_client(
        COMMENT_NODE_ACTIVITY_LOGS_QUERY,
        variables={"nodeId": comment.relay_id},
    )
    content = response.json()

    assert "errors" not in content, content
    node = content["data"]["node"]
    assert node["__typename"] == "Comment"
    edges = node["nodeActivityLogs"]["edges"]
    assert len(edges) == 1

    activity = ActivityLog.objects.get()
    assert edges[0]["node"]["id"] == activity.relay_id
    assert edges[0]["node"]["verb"] == verb
    assert edges[0]["node"]["visibility"] == VisibilityTypes.PUBLIC.name


def test_comment_node_activity_logs_only_include_own_context(
    graphql_user_client, django_user_client
):
    """Each comment is tied to its own activity context; other comments do not appear."""
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    verb = f"{Comment._meta.app_label}.add_comment"
    with pghistory.context(
        user=django_user_client.user.pk,
        visibility=VisibilityTypes.PUBLIC,
        verb=verb,
    ):
        first = CommentFactory()
    with pghistory.context(
        user=django_user_client.user.pk,
        visibility=VisibilityTypes.PUBLIC,
        verb=verb,
    ):
        CommentFactory()

    assert ActivityLog.objects.count() == 2

    response = graphql_user_client(
        COMMENT_NODE_ACTIVITY_LOGS_QUERY,
        variables={"nodeId": first.relay_id},
    )
    content = response.json()

    assert "errors" not in content, content
    edges = content["data"]["node"]["nodeActivityLogs"]["edges"]
    assert len(edges) == 1


def test_comment_object_type_exposes_node_activity_logs_field(
    graphql_user_client, django_user_client
):
    """CommentObjectType surfaces nodeActivityLogs alongside concrete Comment fields."""
    verb = f"{Comment._meta.app_label}.add_comment"
    with pghistory.context(
        user=django_user_client.user.pk,
        visibility=VisibilityTypes.PUBLIC,
        verb=verb,
    ):
        comment = CommentFactory(body="hello")

    response = graphql_user_client(
        COMMENT_WITH_BODY_AND_ACTIVITY_LOGS_QUERY,
        variables={"nodeId": comment.relay_id},
    )
    content = response.json()

    assert "errors" not in content, content
    node = content["data"]["node"]
    assert node["body"] == "hello"
    assert len(node["nodeActivityLogs"]["edges"]) == 1
