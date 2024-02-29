import pytest
import swapper
from django.contrib.auth.models import Permission

from .factories import PageFactory

pytestmark = pytest.mark.django_db

Page = swapper.load_model("baseapp_pages", "Page")


DELETE_MUTATION_QUERY = """
    mutation PageDelete($input: DeleteNodeInput!) {
        deleteNode(input: $input) {
            deletedID
        }
    }
"""


def test_user_cant_delete_page(graphql_user_client):
    page = PageFactory()

    response = graphql_user_client(
        query=DELETE_MUTATION_QUERY,
        variables={
            "input": {
                "id": page.relay_id,
            }
        },
    )

    content = response.json()
    assert content["errors"][0]["message"] == "You don't have permission to delete this."


def test_superuser_can_delete_page(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    page = PageFactory()

    response = graphql_user_client(
        query=DELETE_MUTATION_QUERY,
        variables={
            "input": {
                "id": page.relay_id,
            }
        },
    )

    content = response.json()

    assert content["data"]["deleteNode"]["deletedID"] == page.relay_id
    assert not Page.objects.exists()


def test_owner_can_delete_page(django_user_client, graphql_user_client):
    page = PageFactory(user=django_user_client.user)

    response = graphql_user_client(
        query=DELETE_MUTATION_QUERY,
        variables={
            "input": {
                "id": page.relay_id,
            }
        },
    )

    content = response.json()

    assert content["data"]["deleteNode"]["deletedID"] == page.relay_id
    assert not Page.objects.exists()


def test_user_with_permission_can_delete_page(django_user_client, graphql_user_client):
    perm = Permission.objects.get(content_type__app_label="baseapp_pages", codename="delete_page")
    django_user_client.user.user_permissions.add(perm)

    page = PageFactory()

    response = graphql_user_client(
        query=DELETE_MUTATION_QUERY,
        variables={
            "input": {
                "id": page.relay_id,
            }
        },
    )

    content = response.json()

    assert content["data"]["deleteNode"]["deletedID"] == page.relay_id
    assert not Page.objects.exists()
