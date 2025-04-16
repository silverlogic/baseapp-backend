import pytest
import swapper

pytestmark = pytest.mark.django_db

Organization = swapper.load_model("baseapp_organizations", "Organization")

ORGANIZATION_CREATE_GRAPHQL = """
    mutation OrganizationCreateMutation($input: OrganizationCreateInput!) {
        organizationCreate(input: $input) {
            organization {
                node {
                    id
                }
            }
            profile {
                node {
                    id
                    name
                    image(width: 100, height: 100) {
                        url
                    }
                    urlPath {
                        path
                    }
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""


def test_anon_cant_create_organization(graphql_client):

    response = graphql_client(
        ORGANIZATION_CREATE_GRAPHQL,
        variables={"input": {"name": "my organization"}},
    )
    content = response.json()
    assert content["errors"][0]["message"] == "authentication required"
    assert Organization.objects.count() == 0


def test_user_can_create_organization(graphql_user_client):

    graphql_user_client(
        ORGANIZATION_CREATE_GRAPHQL,
        variables={"input": {"name": "my organization", "urlPath": "my-organization"}},
    )
    organization = Organization.objects.get()
    assert organization.profile.name == "my organization"
    assert organization.profile.url_path.path == "/myorganization"
