import pytest

from .factories import NotificationFactory

pytestmark = pytest.mark.django_db

NOTIFICATIONS_QUERY = """
    query {
        me {
            notifications(unread: true, verbs: "commented,liked") {
                totalCount
                edges {
                    node {
                        id
                        verb
                        level
                        unread
                        data
                        actor { id __typename }
                        target { id }
                        recipient { id }
                    }
                }
            }
        }
    }
"""


def test_notification_fields_and_filters(django_user_client, graphql_user_client) -> None:
    user = django_user_client.user
    liked = NotificationFactory(recipient=user, verb="liked", data={"a": 1})
    NotificationFactory(recipient=user, verb="followed")
    NotificationFactory(recipient=user, verb="commented", unread=False)

    content = graphql_user_client(NOTIFICATIONS_QUERY).json()

    assert "errors" not in content
    connection = content["data"]["me"]["notifications"]
    assert connection["totalCount"] == 1
    node = connection["edges"][0]["node"]
    assert node["id"] == liked.relay_id
    assert node["level"] == "INFO"
    assert node["data"] == {"a": 1}
    assert node["actor"] == {"id": liked.actor.relay_id, "__typename": "User"}
    assert node["target"] is None
    assert node["recipient"] == {"id": user.relay_id}


def test_notification_node_is_visible_to_its_recipient_only(
    django_user_client, graphql_user_client
) -> None:
    mine = NotificationFactory(recipient=django_user_client.user)
    others = NotificationFactory()
    query = "query ($id: ID!) { node(id: $id) { id } }"

    assert graphql_user_client(query, variables={"id": mine.relay_id}).json()["data"]["node"] == {
        "id": mine.relay_id
    }
    assert (
        graphql_user_client(query, variables={"id": others.relay_id}).json()["data"]["node"] is None
    )
