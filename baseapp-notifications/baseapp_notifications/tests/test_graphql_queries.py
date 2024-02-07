import pytest
import swapper

from .factories import NotificationFactory, NotificationSettingFactory

pytestmark = pytest.mark.django_db
NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")


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


def test_user_can_query_notification_settings(django_user_client, graphql_user_client):
    notification_setting = NotificationSettingFactory(
        user=django_user_client.user,
        is_active=True,
        verb="NEW_MESSAGES",
        channel=NotificationSetting.NotificationChannelTypes.EMAIL,
    )

    response = graphql_user_client(
        "query { me { notificationSettings { edges { node { id, channel, verb } }} } }"
    )
    content = response.json()
    assert len(content["data"]["me"]["notificationSettings"]["edges"]) == 1
    assert (
        content["data"]["me"]["notificationSettings"]["edges"][0]["node"]["id"]
        == notification_setting.relay_id
    )
    assert content["data"]["me"]["notificationSettings"]["edges"][0]["node"]["channel"] == "EMAIL"
    assert (
        content["data"]["me"]["notificationSettings"]["edges"][0]["node"]["verb"] == "NEW_MESSAGES"
    )


def test_user_can_query_for_is_notification_setting_active(django_user_client, graphql_user_client):
    NotificationSettingFactory(
        user=django_user_client.user,
        is_active=True,
        verb="NEW_MESSAGES",
        channel=NotificationSetting.NotificationChannelTypes.EMAIL,
    )

    response = graphql_user_client(
        'query { me { isNotificationSettingActive(verb: "NEW_MESSAGES", channel: EMAIL) } }'
    )
    content = response.json()
    assert content["data"]["me"]["isNotificationSettingActive"] is True


def test_user_can_query_for_is_notification_setting_active_when_channel_all_exists(
    django_user_client, graphql_user_client
):
    NotificationSettingFactory(
        user=django_user_client.user,
        is_active=True,
        verb="NEW_MESSAGES",
        channel=NotificationSetting.NotificationChannelTypes.ALL,
    )

    response = graphql_user_client(
        'query { me { isNotificationSettingActive(verb: "NEW_MESSAGES", channel: EMAIL) } }'
    )
    content = response.json()
    assert content["data"]["me"]["isNotificationSettingActive"] is True
