import textwrap

import pytest
from channels.db import database_sync_to_async
from django.contrib.auth.models import Group

from baseapp_core.tests.factories import UserFactory

from .factories import NotificationFactory

QUERY = """
    query {
      me {
        notifications {
          edges { node { id actor { id } target { id } actionObject { id } } }
        }
      }
    }
"""

SUBSCRIPTION_QUERY = textwrap.dedent("""
    subscription op_name {
      onNotificationChange {
        createdNotification { node { id actor { id } target { id } actionObject { id } } }
      }
    }
    """)


@pytest.mark.django_db
def test_objects_without_a_node_type_resolve_to_null(
    django_user_client, graphql_user_client
) -> None:
    # auth.Group has no ObjectType in the schema.
    group = Group.objects.create(name="no node type")
    actor = UserFactory()
    NotificationFactory(
        recipient=django_user_client.user, actor=actor, target=group, action_object=group
    )

    response = graphql_user_client(QUERY)
    content = response.json()

    assert "errors" not in content
    [edge] = content["data"]["me"]["notifications"]["edges"]
    assert edge["node"]["actor"]["id"] == actor.relay_id
    assert edge["node"]["target"] is None
    assert edge["node"]["actionObject"] is None


@pytest.mark.django_db
def test_null_actor_without_a_node_type_resolves_to_null(
    django_user_client, graphql_user_client
) -> None:
    NotificationFactory(recipient=django_user_client.user, actor=Group.objects.create(name="g"))

    content = graphql_user_client(QUERY).json()

    assert "errors" not in content
    [edge] = content["data"]["me"]["notifications"]["edges"]
    assert edge["node"]["actor"] is None
    assert edge["node"]["target"] is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_objects_without_a_node_type_resolve_to_null_over_websocket(
    django_user_client, graphql_ws_user_client
) -> None:
    client = await graphql_ws_user_client(consumer_attrs={"strict_ordering": True})
    sub_id = await client.send(
        msg_type="subscribe",
        payload={"query": SUBSCRIPTION_QUERY, "operationName": "op_name"},
    )
    await client.assert_no_messages()

    def create_notification():
        group = Group.objects.create(name="no node type")
        notification = NotificationFactory(
            recipient=django_user_client.user, target=group, action_object=group
        )
        return notification.relay_id, notification.actor.relay_id

    notification_id, actor_id = await database_sync_to_async(create_notification)()

    resp = await client.receive(assert_id=sub_id, assert_type="next")
    assert "errors" not in resp
    node = resp["data"]["onNotificationChange"]["createdNotification"]["node"]
    assert node["id"] == notification_id
    assert node["actor"]["id"] == actor_id
    assert node["target"] is None
    assert node["actionObject"] is None

    await client.finalize()
