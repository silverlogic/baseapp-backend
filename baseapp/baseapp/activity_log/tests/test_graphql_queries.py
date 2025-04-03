import datetime

import pghistory
import pytest
import swapper

from baseapp.activity_log.models import ActivityLog, VisibilityTypes
from baseapp_comments.tests.factories import CommentFactory
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

Comment = swapper.load_model("baseapp_comments", "Comment")

LIST_ACTIVITY_LOG_GRAPHQL = """
    query ListActivityLog($visibility: VisibilityTypes) {
        activityLogs(visibility: $visibility) {
            edges {
                node {
                    id
                    user {
                        id
                    }
                    verb
                    visibility
                    ipAddress
                    url
                    events {
                        edges {
                            node {
                                obj {
                                    id
                                    __typename
                                }
                            }
                        }
                    }
                }
            }
        }
    }
"""


def test_user_cant_see_private_activity(django_user_client, graphql_user_client):
    with pghistory.context(user=django_user_client.user.pk, visibility=VisibilityTypes.PRIVATE):
        CommentFactory()

    response = graphql_user_client(
        LIST_ACTIVITY_LOG_GRAPHQL,
        variables={},
    )

    content = response.json()

    activity = ActivityLog.objects.get()
    assert activity.visibility == VisibilityTypes.PRIVATE
    assert content["data"]["activityLogs"]["edges"] == []


def test_user_can_see_public_activity(django_user_client, graphql_user_client):
    verb = f"{Comment._meta.app_label}.add_comment"
    with pghistory.context(
        user=django_user_client.user.pk, visibility=VisibilityTypes.PUBLIC, verb=verb
    ):
        comment = CommentFactory()

    response = graphql_user_client(
        LIST_ACTIVITY_LOG_GRAPHQL,
        variables={},
    )

    content = response.json()
    activity = ActivityLog.objects.get()
    assert activity.visibility == VisibilityTypes.PUBLIC
    activity_response = content["data"]["activityLogs"]["edges"][0]["node"]
    assert activity_response["id"] == activity.relay_id
    assert activity_response["user"]["id"] == django_user_client.user.relay_id
    assert activity_response["verb"] == verb
    assert activity_response["visibility"] == VisibilityTypes.PUBLIC.name
    obj_ids = [edge["node"]["obj"]["id"] for edge in activity_response["events"]["edges"]]
    assert comment.relay_id in obj_ids


def test_superuser_can_see_private_activity(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    verb = f"{Comment._meta.app_label}.add_comment"
    with pghistory.context(
        user=django_user_client.user.pk, visibility=VisibilityTypes.PRIVATE, verb=verb
    ):
        CommentFactory()

    response = graphql_user_client(
        LIST_ACTIVITY_LOG_GRAPHQL,
        variables={},
    )

    content = response.json()
    activity = ActivityLog.objects.get()
    assert activity.visibility == VisibilityTypes.PRIVATE
    activity_response = content["data"]["activityLogs"]["edges"][0]["node"]
    assert activity_response["id"] == activity.relay_id
    assert activity_response["user"]["id"] == django_user_client.user.relay_id
    assert activity_response["verb"] == verb
    assert activity_response["visibility"] == VisibilityTypes.PRIVATE.name


def test_user_can_see_node_activity(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()
    verb = f"{Comment._meta.app_label}.add_comment"

    with pghistory.context(
        user=django_user_client.user.pk, visibility=VisibilityTypes.PUBLIC, verb=verb
    ):
        comment = CommentFactory()

    # created another activity
    with pghistory.context(
        user=django_user_client.user.pk, visibility=VisibilityTypes.PUBLIC, verb=verb
    ):
        CommentFactory()

    assert ActivityLog.objects.count() == 2

    response = graphql_user_client(
        """
        query NodeActivityLog($nodeId: ID!) {
            node(id: $nodeId) {
                ... on NodeActivityLogInterface {
                    nodeActivityLogs {
                        edges {
                            node {
                                id
                            }
                        }
                    }
                }
            }
        }
        """,
        variables={"nodeId": comment.relay_id},
    )

    content = response.json()
    assert len(content["data"]["node"]["nodeActivityLogs"]["edges"]) == 1


def test_user_can_see_user_activity(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()
    another_user = UserFactory()
    verb = f"{Comment._meta.app_label}.add_comment"

    with pghistory.context(
        user=django_user_client.user.pk, visibility=VisibilityTypes.PUBLIC, verb=verb
    ):
        CommentFactory()

    # created another activity
    with pghistory.context(user=another_user.pk, visibility=VisibilityTypes.PUBLIC, verb=verb):
        CommentFactory()

    assert ActivityLog.objects.count() == 2

    response = graphql_user_client(
        """
        query UserActivityLog($nodeId: ID!) {
            node(id: $nodeId) {
                ... on User {
                    activityLogs {
                        edges {
                            node {
                                id
                            }
                        }
                    }
                }
            }
        }
        """,
        variables={"nodeId": django_user_client.user.relay_id},
    )

    content = response.json()
    assert len(content["data"]["node"]["activityLogs"]["edges"]) == 1


def test_user_can_see_profile_activity(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()
    profile = ProfileFactory()
    verb = f"{Comment._meta.app_label}.add_comment"

    with pghistory.context(
        user=django_user_client.user.pk,
        profile=django_user_client.user.profile.pk,
        visibility=VisibilityTypes.PUBLIC,
        verb=verb,
    ):
        CommentFactory()

    # created another activity
    with pghistory.context(profile=profile.pk, visibility=VisibilityTypes.PUBLIC, verb=verb):
        CommentFactory()

    assert ActivityLog.objects.count() == 2

    response = graphql_user_client(
        """
        query UserActivityLog($nodeId: ID!) {
            node(id: $nodeId) {
                ... on Profile {
                    activityLogs {
                        edges {
                            node {
                                id
                            }
                        }
                    }
                }
            }
        }
        """,
        variables={"nodeId": django_user_client.user.profile.relay_id},
    )

    content = response.json()

    assert len(content["data"]["node"]["activityLogs"]["edges"]) == 1


def test_user_can_filter_by_user_name(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.first_name = "userA"
    django_user_client.user.last_name = "Doe"

    django_user_client.user.save()

    django_user_client.user.profile.name = django_user_client.user.get_full_name()

    django_user_client.user.profile.save()
    another_user = UserFactory(first_name="USERB", last_name="Collins")

    verb = f"{Comment._meta.app_label}.add_comment"

    with pghistory.context(
        user=django_user_client.user.pk, visibility=VisibilityTypes.PUBLIC, verb=verb
    ):
        CommentFactory()

    # created another  activity

    with pghistory.context(user=another_user.pk, visibility=VisibilityTypes.PUBLIC, verb=verb):

        CommentFactory()

    assert ActivityLog.objects.count() == 2

    response = graphql_user_client(
        """
        query NodeActivityLog {
 activityLogs(userName: "userA") {
    edges {
      node {
        id
         user {
          firstName
        }
      }
    }
  }
        }
        """,
    )

    content = response.json()
    assert len(content["data"]["activityLogs"]["edges"]) == 1


def test_filter_by_user_name_is_case_insensitive(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.first_name = "userA"
    django_user_client.user.last_name = "Doe"

    django_user_client.user.save()

    django_user_client.user.profile.name = django_user_client.user.get_full_name()
    django_user_client.user.profile.save()

    another_user = UserFactory(first_name="USERB", last_name="Collins")

    verb = f"{Comment._meta.app_label}.add_comment"

    with pghistory.context(
        user=django_user_client.user.pk, visibility=VisibilityTypes.PUBLIC, verb=verb
    ):
        CommentFactory()

    # created another activity

    with pghistory.context(user=another_user.pk, visibility=VisibilityTypes.PUBLIC, verb=verb):

        CommentFactory()

    assert ActivityLog.objects.count() == 2

    response = graphql_user_client(
        """
        query NodeActivityLog {
 activityLogs(userName: "user") {
    edges {
      node {
        id
         user {
          firstName
        }
      }
    }
  }
        }
        """,
    )

    content = response.json()
    assert len(content["data"]["activityLogs"]["edges"]) == 2


def test_filter_by_partial_match(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.first_name = "john"
    django_user_client.user.last_name = "Doe"
    django_user_client.user.email = "test01@tsl.io"

    django_user_client.user.save()

    django_user_client.user.profile.name = django_user_client.user.get_full_name()

    django_user_client.user.profile.save()

    another_user = UserFactory(first_name="jean", last_name="Collins", email="test02@tsl.io")

    verb = f"{Comment._meta.app_label}.add_comment"

    with pghistory.context(
        user=django_user_client.user.pk, visibility=VisibilityTypes.PUBLIC, verb=verb
    ):
        CommentFactory()

    # created another  activity

    with pghistory.context(user=another_user.pk, visibility=VisibilityTypes.PUBLIC, verb=verb):

        CommentFactory()

    assert ActivityLog.objects.count() == 2

    response = graphql_user_client(
        """
        query NodeActivityLog {
 activityLogs(userName: "jo") {
    edges {
      node {
        id
         user {
          firstName
          lastName
       profile {
            name
          }
        }
      }
    }
  }
        }
        """,
    )

    content = response.json()
    assert len(content["data"]["activityLogs"]["edges"]) == 1


def test_invalid_date_range_created_from_after_created_to(django_user_client, graphql_user_client):
    now = datetime.date.today()
    created_from = now + datetime.timedelta(days=1)
    created_to = now - datetime.timedelta(days=1)

    response = graphql_user_client(
        """
        query ActivityLogs($createdFrom: Date, $createdTo: Date) {
            activityLogs(createdFrom: $createdFrom, createdTo: $createdTo) {
                edges {
                    node {
                        id
                    }
                }
            }
        }
        """,
        variables={
            "createdFrom": created_from.isoformat(),
            "createdTo": created_to.isoformat(),
        },
    )

    content = response.json()
    assert "errors" in content
    error_messages = [error["message"] for error in content["errors"]]
    assert any(
        "`created_from` must be earlier than or equal to `created_to`." in message
        for message in error_messages
    )
