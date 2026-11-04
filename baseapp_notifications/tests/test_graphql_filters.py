import pytest

from baseapp_notifications.groups import register_notification_group

from .factories import NotificationFactory

pytestmark = pytest.mark.django_db

QUERY = """
    query Notifications($group: String) {
        me { notifications(group: $group) { edges { node { verb } } } }
    }
"""


def verbs(graphql_user_client, group) -> set[str]:
    response = graphql_user_client(QUERY, variables={"group": group})
    edges = response.json()["data"]["me"]["notifications"]["edges"]
    return {edge["node"]["verb"] for edge in edges}


@pytest.fixture
def notifications(django_user_client) -> None:
    for verb in ["chats", "chats.new", "chats.mentions.reply", "chatsroom.new", "billing.paid"]:
        NotificationFactory(recipient=django_user_client.user, verb=verb)
    NotificationFactory(verb="chats.new")  # someone else's


def test_group_filter_matches_key_and_prefix(
    notification_groups_registry, notifications, graphql_user_client
) -> None:
    assert verbs(graphql_user_client, "chats") == {"chats", "chats.new", "chats.mentions.reply"}
    assert verbs(graphql_user_client, "chats.mentions") == {"chats.mentions.reply"}
    assert verbs(graphql_user_client, "unknown") == set()


def test_group_filter_includes_explicit_verbs_of_a_registered_group(
    notification_groups_registry, notifications, graphql_user_client
) -> None:
    register_notification_group("money", label="Money", verbs=["billing.paid"])

    assert verbs(graphql_user_client, "money") == {"billing.paid"}


def test_no_group_returns_everything(notifications, graphql_user_client) -> None:
    assert len(verbs(graphql_user_client, None)) == 5
