import pytest

from .factories import NotificationFactory, NotificationSettingFactory

pytestmark = pytest.mark.django_db
import swapper

NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")


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


NOTIFICATION_SETTINGS_TOGGLE_GRAPHQL = """
    mutation NotificationSettingToggleMutation($input: NotificationSettingToggleInput!) {
        notificationSettingToggle(input: $input) {
            notificationSetting {
                channel
                verb
                isActive
            }
        }
    }
"""


def test_user_can_enable_notification_setting(django_user_client, graphql_user_client):
    response = graphql_user_client(
        NOTIFICATION_SETTINGS_TOGGLE_GRAPHQL,
        variables={
            "input": {
                "verb": "NEW_MESSAGES",
                "channel": "EMAIL",
            }
        },
    )

    content = response.json()
    assert (
        content["data"]["notificationSettingToggle"]["notificationSetting"]["verb"]
        == "NEW_MESSAGES"
    )
    assert content["data"]["notificationSettingToggle"]["notificationSetting"]["channel"] == "EMAIL"
    assert content["data"]["notificationSettingToggle"]["notificationSetting"]["isActive"] is False
    assert django_user_client.user.notifications_settings.filter(
        verb="NEW_MESSAGES", channel=NotificationSetting.NotificationChannelTypes.EMAIL
    ).exists()


def test_user_can_disable_notification_setting(django_user_client, graphql_user_client):
    notification_setting = NotificationSettingFactory(
        user=django_user_client.user,
        is_active=True,
        verb="NEW_MESSAGES",
        channel=NotificationSetting.NotificationChannelTypes.EMAIL,
    )
    response = graphql_user_client(
        NOTIFICATION_SETTINGS_TOGGLE_GRAPHQL,
        variables={
            "input": {
                "verb": "NEW_MESSAGES",
                "channel": "EMAIL",
            }
        },
    )

    content = response.json()
    assert content["data"]["notificationSettingToggle"]["notificationSetting"]["isActive"] is False
    assert (
        content["data"]["notificationSettingToggle"]["notificationSetting"]["verb"]
        == "NEW_MESSAGES"
    )
    assert content["data"]["notificationSettingToggle"]["notificationSetting"]["channel"] == "EMAIL"
    notification_setting.refresh_from_db()
    assert notification_setting.is_active is False


def test_user_can_enable_all_notification_setting(django_user_client, graphql_user_client):
    notification_setting = NotificationSettingFactory(
        user=django_user_client.user,
        is_active=False,
        verb="NEW_MESSAGES",
        channel=NotificationSetting.NotificationChannelTypes.EMAIL,
    )
    NotificationSettingFactory(
        user=django_user_client.user,
        is_active=False,
        verb="NEW_MESSAGES",
        channel=NotificationSetting.NotificationChannelTypes.ALL,
    )
    response = graphql_user_client(
        NOTIFICATION_SETTINGS_TOGGLE_GRAPHQL,
        variables={
            "input": {
                "verb": "NEW_MESSAGES",
                "channel": "ALL",
            }
        },
    )

    content = response.json()
    assert content["data"]["notificationSettingToggle"]["notificationSetting"]["isActive"] is True
    assert (
        content["data"]["notificationSettingToggle"]["notificationSetting"]["verb"]
        == "NEW_MESSAGES"
    )
    assert content["data"]["notificationSettingToggle"]["notificationSetting"]["channel"] == "ALL"
    notification_setting.refresh_from_db()
    assert notification_setting.is_active is True
    assert django_user_client.user.notifications_settings.filter(
        verb="NEW_MESSAGES",
        channel=NotificationSetting.NotificationChannelTypes.EMAIL,
        is_active=True,
    ).exists()


def test_user_can_disable_all_notification_setting(django_user_client, graphql_user_client):
    notification_setting = NotificationSettingFactory(
        user=django_user_client.user,
        is_active=True,
        verb="NEW_MESSAGES",
        channel=NotificationSetting.NotificationChannelTypes.EMAIL,
    )
    NotificationSettingFactory(
        user=django_user_client.user,
        is_active=True,
        verb="NEW_MESSAGES",
        channel=NotificationSetting.NotificationChannelTypes.ALL,
    )

    response = graphql_user_client(
        NOTIFICATION_SETTINGS_TOGGLE_GRAPHQL,
        variables={
            "input": {
                "verb": "NEW_MESSAGES",
                "channel": "ALL",
            }
        },
    )

    content = response.json()
    assert content["data"]["notificationSettingToggle"]["notificationSetting"]["isActive"] is False
    assert (
        content["data"]["notificationSettingToggle"]["notificationSetting"]["verb"]
        == "NEW_MESSAGES"
    )
    assert content["data"]["notificationSettingToggle"]["notificationSetting"]["channel"] == "ALL"
    notification_setting.refresh_from_db()
    assert notification_setting.is_active is False
    assert django_user_client.user.notifications_settings.filter(
        verb="NEW_MESSAGES",
        channel=NotificationSetting.NotificationChannelTypes.EMAIL,
        is_active=False,
    ).exists()


def test_user_can_disable_all_notification_setting_first_time_with_active(
    django_user_client, graphql_user_client
):
    notification_setting = NotificationSettingFactory(
        user=django_user_client.user,
        is_active=True,
        verb="NEW_MESSAGES",
        channel=NotificationSetting.NotificationChannelTypes.EMAIL,
    )

    response = graphql_user_client(
        NOTIFICATION_SETTINGS_TOGGLE_GRAPHQL,
        variables={
            "input": {
                "verb": "NEW_MESSAGES",
                "channel": "ALL",
            }
        },
    )

    content = response.json()
    assert content["data"]["notificationSettingToggle"]["notificationSetting"]["isActive"] is False
    assert (
        content["data"]["notificationSettingToggle"]["notificationSetting"]["verb"]
        == "NEW_MESSAGES"
    )
    assert content["data"]["notificationSettingToggle"]["notificationSetting"]["channel"] == "ALL"
    notification_setting.refresh_from_db()
    assert notification_setting.is_active is False
    assert django_user_client.user.notifications_settings.filter(
        verb="NEW_MESSAGES",
        channel=NotificationSetting.NotificationChannelTypes.EMAIL,
        is_active=False,
    ).exists()

    response = graphql_user_client(
        'query { me { isNotificationSettingActive(verb: "NEW_MESSAGES", channel: EMAIL) } }'
    )
    content = response.json()
    assert not content["data"]["me"]["isNotificationSettingActive"]


def test_user_can_disable_all_notification_setting_first_time_with_non_active(
    django_user_client, graphql_user_client
):
    notification_setting = NotificationSettingFactory(
        user=django_user_client.user,
        is_active=False,
        verb="NEW_MESSAGES",
        channel=NotificationSetting.NotificationChannelTypes.EMAIL,
    )

    response = graphql_user_client(
        NOTIFICATION_SETTINGS_TOGGLE_GRAPHQL,
        variables={
            "input": {
                "verb": "NEW_MESSAGES",
                "channel": "ALL",
            }
        },
    )

    content = response.json()
    assert content["data"]["notificationSettingToggle"]["notificationSetting"]["isActive"] is False
    assert (
        content["data"]["notificationSettingToggle"]["notificationSetting"]["verb"]
        == "NEW_MESSAGES"
    )
    assert content["data"]["notificationSettingToggle"]["notificationSetting"]["channel"] == "ALL"
    notification_setting.refresh_from_db()
    assert notification_setting.is_active is False
    assert not django_user_client.user.notifications_settings.filter(
        verb="NEW_MESSAGES",
        channel=NotificationSetting.NotificationChannelTypes.EMAIL,
        is_active=True,
    ).exists()

    response = graphql_user_client(
        'query { me { isNotificationSettingActive(verb: "NEW_MESSAGES", channel: EMAIL) } }'
    )
    content = response.json()
    assert content["data"]["me"]["isNotificationSettingActive"] is False
