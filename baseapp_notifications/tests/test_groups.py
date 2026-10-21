import pytest
import swapper
from django.core.exceptions import ImproperlyConfigured

from baseapp_core.tests.factories import UserFactory
from baseapp_notifications.groups import (
    get_notification_group,
    get_notification_group_for_verb,
    is_registered_verb,
    list_notification_groups,
    register_notification_group,
)
from baseapp_notifications.utils import (
    can_user_receive_notification,
    get_notification_group_states,
    set_notification_group_setting,
)

from .factories import NotificationSettingFactory

pytestmark = pytest.mark.django_db

NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
Channels = NotificationSetting.NotificationChannelTypes


def states_by_channel(user, group) -> dict[int, bool]:
    [state] = get_notification_group_states(user, [group])
    return {channel.channel: channel.is_active for channel in state.channels}


# Registry


def test_register_defaults(notification_groups_registry) -> None:
    group = register_notification_group("comments", label="Comments")

    assert get_notification_group("comments") is group
    assert group.description == ""
    assert group.verbs is None
    assert group.is_locked is False
    assert group.channels == (Channels.IN_APP, Channels.EMAIL, Channels.PUSH)


def test_register_again_replaces_in_place(notification_groups_registry) -> None:
    register_notification_group("a", label="A")
    register_notification_group("b", label="B")
    register_notification_group("a", label="A2")

    assert [group.key for group in list_notification_groups()] == ["a", "b"]
    assert get_notification_group("a").label == "A2"


def test_channels_accept_members_values_and_names(notification_groups_registry) -> None:
    group = register_notification_group(
        "billing", label="Billing", channels=["email", Channels.IN_APP, 1]
    )

    assert group.channels == (Channels.EMAIL, Channels.IN_APP)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"key": ""},
        {"key": "_ALL_"},
        {"key": "x", "channels": [Channels.ALL]},
        {"key": "x", "channels": ["fax"]},
        {"key": "x", "channels": [42]},
        {"key": "x", "channels": []},
        {"key": "x", "audience": "staff"},
    ],
)
def test_register_rejects_invalid_groups(notification_groups_registry, kwargs) -> None:
    key = kwargs.pop("key")
    with pytest.raises(ImproperlyConfigured):
        register_notification_group(key, label="Label", **kwargs)


def test_list_filters_by_audience(notification_groups_registry) -> None:
    register_notification_group("everyone", label="Everyone")
    register_notification_group("staff", label="Staff", audience=lambda user: user.is_staff)

    assert [g.key for g in list_notification_groups()] == ["everyone", "staff"]
    assert [g.key for g in list_notification_groups(UserFactory())] == ["everyone"]
    assert [g.key for g in list_notification_groups(UserFactory(is_staff=True))] == [
        "everyone",
        "staff",
    ]


def test_verb_lookup(notification_groups_registry) -> None:
    chats = register_notification_group("chats", label="Chats")
    mentions = register_notification_group("chats.mentions", label="Mentions")
    security = register_notification_group(
        "security", label="Security", verbs=["security.new_login", "password_changed"]
    )

    assert get_notification_group_for_verb("chats") is chats
    assert get_notification_group_for_verb("chats.new_message") is chats
    assert get_notification_group_for_verb("chats.mentions") is mentions
    assert get_notification_group_for_verb("chats.mentions.reply") is mentions
    assert get_notification_group_for_verb("password_changed") is security
    assert get_notification_group_for_verb("security") is security
    assert get_notification_group_for_verb("security.other") is None
    assert get_notification_group_for_verb("chatsroom") is None

    assert is_registered_verb("chats.new_message")
    assert not is_registered_verb("unregistered")


# Delivery resolution


def test_unregistered_verbs_resolve_as_before(notification_groups_registry) -> None:
    user = UserFactory()
    assert can_user_receive_notification(user.id, "CHATS.NEW", Channels.EMAIL) is True

    NotificationSettingFactory(user=user, verb="CHATS", channel=Channels.EMAIL, is_active=False)
    assert can_user_receive_notification(user.id, "CHATS.NEW", Channels.EMAIL) is False
    assert can_user_receive_notification(user.id, "CHATS.NEW", Channels.PUSH) is True


def test_group_key_setting_mutes_every_verb_of_the_group(notification_groups_registry) -> None:
    register_notification_group("chats.mentions", label="Mentions")
    register_notification_group("digest", label="Digest", verbs=["weekly_summary"])
    user = UserFactory()
    NotificationSettingFactory(
        user=user, verb="chats.mentions", channel=Channels.ALL, is_active=False
    )
    NotificationSettingFactory(user=user, verb="digest", channel=Channels.EMAIL, is_active=False)

    assert can_user_receive_notification(user.id, "chats.mentions.reply", Channels.PUSH) is False
    assert can_user_receive_notification(user.id, "chats.new_message", Channels.PUSH) is True
    assert can_user_receive_notification(user.id, "weekly_summary", Channels.EMAIL) is False
    assert can_user_receive_notification(user.id, "weekly_summary", Channels.IN_APP) is True


def test_legacy_first_segment_setting_still_applies(notification_groups_registry) -> None:
    register_notification_group("chats.mentions", label="Mentions")
    user = UserFactory()
    NotificationSettingFactory(user=user, verb="chats", channel=Channels.EMAIL, is_active=False)

    assert can_user_receive_notification(user.id, "chats.mentions.reply", Channels.EMAIL) is False


def test_locked_group_is_always_delivered(notification_groups_registry) -> None:
    group = register_notification_group("security", label="Security", is_locked=True)
    user = UserFactory()
    NotificationSettingFactory(user=user, verb="security", channel=Channels.ALL, is_active=False)
    NotificationSettingFactory(user=user, verb="_ALL_", channel=Channels.ALL, is_active=False)

    assert can_user_receive_notification(user.id, "security.new_login", Channels.EMAIL) is True
    assert all(states_by_channel(user, group).values())


SCENARIOS = [
    [],
    [("g", Channels.EMAIL, False)],
    [("g", Channels.EMAIL, True), ("g", Channels.PUSH, False)],
    [("g", Channels.ALL, False)],
    [("g", Channels.ALL, False), ("g", Channels.EMAIL, True)],
    [("g", Channels.ALL, True), ("g", Channels.IN_APP, False)],
    [("_ALL_", Channels.PUSH, False)],
    [("_ALL_", Channels.ALL, False)],
    [("other", Channels.ALL, False)],
]


@pytest.mark.parametrize("rows", SCENARIOS)
def test_group_states_match_can_user_receive_notification(
    notification_groups_registry, rows, django_assert_num_queries
) -> None:
    group = register_notification_group("g", label="G")
    user = UserFactory()
    for verb, channel, is_active in rows:
        NotificationSettingFactory(user=user, verb=verb, channel=channel, is_active=is_active)

    with django_assert_num_queries(1):
        states = states_by_channel(user, group)

    for channel in group.channels:
        assert states[channel] == can_user_receive_notification(user.id, "g.event", channel)


def test_group_states_without_groups_runs_no_query(django_assert_num_queries) -> None:
    with django_assert_num_queries(0):
        assert get_notification_group_states(UserFactory.build(), []) == []


def test_group_state_exposes_metadata(notification_groups_registry) -> None:
    group = register_notification_group("g", label="Label", description="", is_locked=True)

    [state] = get_notification_group_states(UserFactory(), [group])

    assert (state.key, state.label, state.description, state.is_locked) == (
        "g",
        "Label",
        None,
        True,
    )


# Setting preferences


def test_set_channel_is_idempotent(notification_groups_registry) -> None:
    group = register_notification_group("g", label="G")
    user = UserFactory()

    for _ in range(2):
        set_notification_group_setting(user, group, Channels.EMAIL, False)

    assert NotificationSetting.objects.filter(user=user, verb="g").count() == 1
    assert states_by_channel(user, group) == {
        Channels.IN_APP: True,
        Channels.EMAIL: False,
        Channels.PUSH: True,
    }

    for _ in range(2):
        set_notification_group_setting(user, group, Channels.EMAIL, True)

    assert all(states_by_channel(user, group).values())


def test_set_all_sets_every_channel(notification_groups_registry) -> None:
    group = register_notification_group("g", label="G")
    user = UserFactory()

    set_notification_group_setting(user, group, Channels.ALL, False)
    assert not any(states_by_channel(user, group).values())

    set_notification_group_setting(user, group, Channels.ALL, True)
    assert all(states_by_channel(user, group).values())


def test_enabling_one_channel_under_a_muted_all_keeps_the_others_off(
    notification_groups_registry,
) -> None:
    group = register_notification_group("g", label="G")
    user = UserFactory()
    # e.g. left behind by notificationSettingToggle on ALL
    NotificationSettingFactory(user=user, verb="g", channel=Channels.ALL, is_active=False)

    set_notification_group_setting(user, group, Channels.PUSH, True)

    assert states_by_channel(user, group) == {
        Channels.IN_APP: False,
        Channels.EMAIL: False,
        Channels.PUSH: True,
    }
