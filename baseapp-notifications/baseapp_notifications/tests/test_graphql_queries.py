import pytest

from .factories import NotificationFactory

pytestmark = pytest.mark.django_db


def test_user_can_query_notifications_unread_count(django_user_client, graphql_user_client):
    NotificationFactory(recipient=django_user_client.user)

    response = graphql_user_client("query { me { notificationsUnreadCount } }")
    content = response.json()
    assert content["data"]["me"]["notificationsUnreadCount"] == 1


def test_user_can_query_notifications(django_user_client, graphql_user_client):
    notification = NotificationFactory(recipient=django_user_client.user)

    response = graphql_user_client("query { me { notifications { edges { node { id } }} } }")
    content = response.json()
    assert content["data"]["me"]["notifications"]["edges"][0]["node"]["id"] == notification.relay_id


def test_another_user_cant_query_notifications(graphql_user_client):
    NotificationFactory()

    response = graphql_user_client("query { me { notifications { edges { node { id } }} } }")
    content = response.json()
    assert len(content["data"]["me"]["notifications"]["edges"]) == 0
