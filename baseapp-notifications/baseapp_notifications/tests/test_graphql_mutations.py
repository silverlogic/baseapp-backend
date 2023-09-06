import pytest

from .factories import NotificationFactory

pytestmark = pytest.mark.django_db


def test_user_can_notifications_mark_all_as_read(django_user_client, graphql_user_client):
    NotificationFactory(recipient=django_user_client.user)
    notification = NotificationFactory(recipient=django_user_client.user)
    assert notification.unread is True

    response = graphql_user_client(
        "mutation { notificationsMarkAllAsRead(input: { read: true }) { recipient { notificationsUnreadCount } } }",
    )

    content = response.json()
    assert (
        content["data"]["notificationsMarkAllAsRead"]["recipient"]["notificationsUnreadCount"] == 0
    )

    notification.refresh_from_db()
    assert notification.unread is False


def test_another_user_cant_notifications_mark_all_as_read(graphql_user_client):
    notification = NotificationFactory()
    assert notification.unread is True

    graphql_user_client(
        "mutation { notificationsMarkAllAsRead(input: { read: true }) { recipient { notificationsUnreadCount } } }",
    )

    notification.refresh_from_db()
    assert notification.unread is True


def test_user_can_notifications_mark_as_read(django_user_client, graphql_user_client):
    NotificationFactory(recipient=django_user_client.user)
    notification = NotificationFactory(recipient=django_user_client.user)
    assert notification.unread is True

    response = graphql_user_client(
        'mutation { notificationsMarkAsRead(input: { notificationIds: ["%s"], read: true }) { recipient { notificationsUnreadCount } } }'
        % notification.relay_id
    )

    content = response.json()
    assert content["data"]["notificationsMarkAsRead"]["recipient"]["notificationsUnreadCount"] == 1

    notification.refresh_from_db()
    assert notification.unread is False


def test_another_user_cant_notifications_mark_as_read(graphql_user_client):
    notification = NotificationFactory()
    assert notification.unread is True

    response = graphql_user_client(
        'mutation { notificationsMarkAsRead(input: { notificationIds: ["%s"], read: true }) { recipient { notificationsUnreadCount } } }'
        % notification.relay_id
    )

    content = response.json()
    assert content["data"]["notificationsMarkAsRead"]["recipient"]["notificationsUnreadCount"] == 0

    notification.refresh_from_db()
    assert notification.unread is True
