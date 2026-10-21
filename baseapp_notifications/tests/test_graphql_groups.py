import pytest
import swapper

from baseapp_notifications.groups import register_notification_group

from .factories import NotificationSettingFactory

pytestmark = pytest.mark.django_db

NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
Channels = NotificationSetting.NotificationChannelTypes

GROUP_FIELDS = "key label description isLocked channels { channel isActive }"

GROUPS_QUERY = "query { me { notificationSettingGroups { %s } } }" % GROUP_FIELDS

UPDATE_MUTATION = """
    mutation NotificationSettingsUpdate($input: NotificationSettingsUpdateInput!) {
        notificationSettingsUpdate(input: $input) {
            groups { %s }
            recipient { notificationSettingGroups { key } }
            errors { field messages }
        }
    }
""" % GROUP_FIELDS


@pytest.fixture
def groups(notification_groups_registry) -> None:
    register_notification_group(
        "comments", label="Comments", description="Replies to your comments"
    )
    register_notification_group("billing", label="Billing", channels=["EMAIL"])
    register_notification_group("security", label="Security", is_locked=True)
    register_notification_group("staff", label="Staff", audience=lambda user: user.is_staff)


def update(graphql_user_client, *settings) -> dict:
    response = graphql_user_client(
        UPDATE_MUTATION,
        variables={
            "input": {
                "settings": [
                    {"group": group, "channel": channel, "isActive": is_active}
                    for group, channel, is_active in settings
                ]
            }
        },
    )
    content = response.json()
    assert "errors" not in content, content
    return content["data"]["notificationSettingsUpdate"]


def channels(group: dict) -> dict[str, bool]:
    return {channel["channel"]: channel["isActive"] for channel in group["channels"]}


def test_query_groups(groups, django_user_client, graphql_user_client) -> None:
    NotificationSettingFactory(
        user=django_user_client.user, verb="comments", channel=Channels.PUSH, is_active=False
    )

    response = graphql_user_client(GROUPS_QUERY)
    content = response.json()

    assert content["data"]["me"]["notificationSettingGroups"] == [
        {
            "key": "comments",
            "label": "Comments",
            "description": "Replies to your comments",
            "isLocked": False,
            "channels": [
                {"channel": "IN_APP", "isActive": True},
                {"channel": "EMAIL", "isActive": True},
                {"channel": "PUSH", "isActive": False},
            ],
        },
        {
            "key": "billing",
            "label": "Billing",
            "description": None,
            "isLocked": False,
            "channels": [{"channel": "EMAIL", "isActive": True}],
        },
        {
            "key": "security",
            "label": "Security",
            "description": None,
            "isLocked": True,
            "channels": [
                {"channel": "IN_APP", "isActive": True},
                {"channel": "EMAIL", "isActive": True},
                {"channel": "PUSH", "isActive": True},
            ],
        },
    ]


def test_query_groups_respects_audience(groups, django_user_client, graphql_user_client) -> None:
    django_user_client.user.is_staff = True
    django_user_client.user.save()

    response = graphql_user_client("query { me { notificationSettingGroups { key } } }")

    keys = [group["key"] for group in response.json()["data"]["me"]["notificationSettingGroups"]]
    assert keys == ["comments", "billing", "security", "staff"]


def test_query_groups_empty_without_registry(
    notification_groups_registry, graphql_user_client
) -> None:
    response = graphql_user_client(GROUPS_QUERY)
    assert response.json()["data"]["me"]["notificationSettingGroups"] == []


def test_query_groups_of_another_user_is_empty(groups, graphql_user_client) -> None:
    from baseapp_core.tests.factories import UserFactory

    other = UserFactory()
    response = graphql_user_client(
        'query { user(id: "%s") { notificationSettingGroups { key } } }' % other.relay_id
    )
    assert response.json()["data"]["user"]["notificationSettingGroups"] == []


def test_update_sets_channels_idempotently(groups, django_user_client, graphql_user_client) -> None:
    for _ in range(2):
        payload = update(graphql_user_client, ("comments", "EMAIL", False))

    assert payload["errors"] is None
    [group] = payload["groups"]
    assert group["key"] == "comments"
    assert channels(group) == {"IN_APP": True, "EMAIL": False, "PUSH": True}
    assert payload["recipient"]["notificationSettingGroups"][0]["key"] == "comments"
    assert (
        NotificationSetting.objects.filter(user=django_user_client.user, verb="comments").count()
        == 1
    )

    for _ in range(2):
        payload = update(graphql_user_client, ("comments", "EMAIL", True))
    assert all(channels(payload["groups"][0]).values())


def test_update_many_settings_returns_each_group_once(groups, graphql_user_client) -> None:
    payload = update(
        graphql_user_client,
        ("comments", "ALL", False),
        ("billing", "EMAIL", False),
        ("comments", "PUSH", True),
    )

    assert [group["key"] for group in payload["groups"]] == ["comments", "billing"]
    assert channels(payload["groups"][0]) == {"IN_APP": False, "EMAIL": False, "PUSH": True}
    assert channels(payload["groups"][1]) == {"EMAIL": False}


@pytest.mark.parametrize(
    "setting, message",
    [
        (("unknown", "EMAIL", False), "Unknown notification group: unknown"),
        (("staff", "EMAIL", False), "Unknown notification group: staff"),
        (("security", "EMAIL", False), "Notification group security cannot be changed"),
        (("billing", "PUSH", False), "Notification group billing has no Push channel"),
    ],
)
def test_update_rejects_invalid_settings(
    groups, django_user_client, graphql_user_client, setting, message
) -> None:
    payload = update(graphql_user_client, ("comments", "EMAIL", False), setting)

    assert payload["groups"] is None
    assert payload["errors"] == [{"field": "settings", "messages": [message]}]
    # nothing is applied when any entry is invalid
    assert not NotificationSetting.objects.filter(user=django_user_client.user).exists()


def test_update_requires_login(groups, graphql_client) -> None:
    response = graphql_client(
        UPDATE_MUTATION,
        variables={
            "input": {"settings": [{"group": "comments", "channel": "ALL", "isActive": False}]}
        },
    )
    content = response.json()
    assert content["errors"][0]["extensions"]["code"] == "authentication_required"
    assert not NotificationSetting.objects.exists()
