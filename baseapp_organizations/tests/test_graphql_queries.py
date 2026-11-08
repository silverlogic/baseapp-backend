import pytest
import swapper

pytestmark = pytest.mark.django_db

Organization = swapper.load_model("baseapp_organizations", "Organization")

ORGANIZATION_QUERY = """
    query Organization($id: ID!) {
        organization(id: $id) {
            pk
            profile { name }
            canChange: hasPerm(perm: "change")
        }
    }
"""


def test_superuser_can_view_organization(django_user_client, graphql_user_client) -> None:
    django_user_client.user.is_superuser = True
    django_user_client.user.save()
    organization = Organization.objects.create(name="Acme")

    response = graphql_user_client(ORGANIZATION_QUERY, variables={"id": organization.relay_id})

    assert response.json()["data"]["organization"] == {
        "pk": organization.pk,
        "profile": None,
        "canChange": True,
    }


def test_user_cant_view_organization(graphql_user_client) -> None:
    organization = Organization.objects.create(name="Acme")

    response = graphql_user_client(ORGANIZATION_QUERY, variables={"id": organization.relay_id})

    assert response.json()["data"]["organization"] is None
