import pytest
from baseapp_core.tests.factories import UserFactory
from django.contrib.auth.models import Permission

pytestmark = pytest.mark.django_db

QUERY = """
    query GetUser($id: ID!) {
        user(id: $id) {
            id
            pk
            isAuthenticated
            email
        }
    }
"""


def test_anon_can_query_user_by_pk(graphql_client):
    user = UserFactory()
    response = graphql_client(QUERY, variables={"id": user.pk})
    content = response.json()

    assert content["data"]["user"]["id"] == user.relay_id
    assert content["data"]["user"]["pk"] == user.pk
    assert content["data"]["user"]["isAuthenticated"] is False
    assert content["data"]["user"]["email"] is None


def test_user_can_query_user_by_relay_id(django_user_client, graphql_user_client):
    user = UserFactory()
    response = graphql_user_client(QUERY, variables={"id": user.relay_id})
    content = response.json()

    assert content["data"]["user"]["id"] == user.relay_id
    assert content["data"]["user"]["isAuthenticated"] is False


def test_user_cant_view_others_private_field(django_user_client, graphql_user_client):
    user = UserFactory()
    response = graphql_user_client(QUERY, variables={"id": user.relay_id})
    content = response.json()

    assert content["data"]["user"]["email"] is None


def test_staff_can_view_others_private_field(django_user_client, graphql_user_client):
    django_user_client.user.is_staff = True
    django_user_client.user.save()

    user = UserFactory()
    response = graphql_user_client(QUERY, variables={"id": user.relay_id})
    content = response.json()

    assert content["data"]["user"]["email"] == user.email


def test_superuser_can_view_others_private_field(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    user = UserFactory()
    response = graphql_user_client(QUERY, variables={"id": user.relay_id})
    content = response.json()

    assert content["data"]["user"]["email"] == user.email


def test_user_with_perm_can_view_others_private_field(django_user_client, graphql_user_client):
    user = UserFactory()

    perm = Permission.objects.get(
        content_type__app_label=user._meta.app_label, codename="view_user_email"
    )
    django_user_client.user.user_permissions.add(perm)

    response = graphql_user_client(QUERY, variables={"id": user.relay_id})
    content = response.json()

    assert content["data"]["user"]["email"] == user.email
