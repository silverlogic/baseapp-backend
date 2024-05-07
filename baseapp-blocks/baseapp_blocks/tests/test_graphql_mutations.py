import pytest
import swapper
from baseapp_core.tests.factories import UserFactory

Block = swapper.load_model("baseapp_blocks", "Block")

pytestmark = pytest.mark.django_db

BLOCK_TOGGLE_GRAPHQL = """
mutation BlockToggle($input: BlockToggleInput!) {
  blockToggle(input: $input) {
    block {
      node {
        id
      }
    }
    target {
      id
      blockersCount
    }
    actor {
      id
      blockingCount
    }
  }
}
"""


def test_anon_cant_block(graphql_client):
    user1 = UserFactory()
    user2 = UserFactory()

    variables = {
        "input": {
            "actorObjectId": user1.relay_id,
            "targetObjectId": user2.relay_id,
        }
    }

    response = graphql_client(BLOCK_TOGGLE_GRAPHQL, variables=variables)

    content = response.json()
    assert content["errors"][0]["message"] == "authentication required"
    assert Block.objects.count() == 0


def test_user_can_block(django_user_client, graphql_user_client):
    user1 = django_user_client.user
    user2 = UserFactory()

    variables = {
        "input": {
            "actorObjectId": user1.relay_id,
            "targetObjectId": user2.relay_id,
        }
    }

    response = graphql_user_client(BLOCK_TOGGLE_GRAPHQL, variables=variables)

    content = response.json()

    assert content["data"]["blockToggle"]["actor"]["blockingCount"] == 1

    # User shouldn't see this count
    assert content["data"]["blockToggle"]["target"]["blockersCount"] is None


def test_user_can_unblock(django_user_client, graphql_user_client):
    user1 = django_user_client.user
    user2 = UserFactory()

    variables = {
        "input": {
            "actorObjectId": user1.relay_id,
            "targetObjectId": user2.relay_id,
        }
    }

    response = graphql_user_client(BLOCK_TOGGLE_GRAPHQL, variables=variables)
    content = response.json()

    assert content["data"]["blockToggle"]["actor"]["blockingCount"] == 1

    # User shouldn't see this count
    assert content["data"]["blockToggle"]["target"]["blockersCount"] is None

    response = graphql_user_client(BLOCK_TOGGLE_GRAPHQL, variables=variables)
    content = response.json()

    assert content["data"]["blockToggle"]["actor"]["blockingCount"] == 0

    # User shouldn't see this count
    assert content["data"]["blockToggle"]["target"]["blockersCount"] is None


def test_user_cant_unblock_others_block(django_user_client, graphql_user_client):
    user1 = django_user_client.user
    user2 = UserFactory()
    user3 = UserFactory()

    variables = {
        "input": {
            "actorObjectId": user1.relay_id,
            "targetObjectId": user2.relay_id,
        }
    }

    response = graphql_user_client(BLOCK_TOGGLE_GRAPHQL, variables=variables)
    content = response.json()

    # User shouldn't see this count
    assert content["data"]["blockToggle"]["target"]["blockersCount"] is None

    assert content["data"]["blockToggle"]["actor"]["blockingCount"] == 1

    variables = {
        "input": {
            "actorObjectId": user3.relay_id,
            "targetObjectId": user2.relay_id,
        }
    }

    response = graphql_user_client(BLOCK_TOGGLE_GRAPHQL, variables=variables)
    content = response.json()

    assert content["errors"][0]["message"] == "You don't have permission to perform this action"
    assert content["errors"][0]["extensions"]["code"] == "permission_required"
