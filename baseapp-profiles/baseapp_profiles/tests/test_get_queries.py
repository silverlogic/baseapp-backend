import pytest
import swapper

from .factories import ProfileFactory

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")

GET_PROFILE_BY_PATH = """
    query Profile($id: ID!) {
        profile(id: $id) {
            id
            name
            metadata {
                metaTitle
                metaOgImage(width: 100, height: 100) {
                    url
                }
            }
        }
    }
"""


def test_profile_metadata(graphql_user_client, image_djangofile):
    profile = ProfileFactory(image=image_djangofile)

    response = graphql_user_client(GET_PROFILE_BY_PATH, variables={"id": profile.relay_id})
    content = response.json()
    assert content["data"]["profile"]["id"] == profile.relay_id
    assert content["data"]["profile"]["name"] == profile.name
    assert content["data"]["profile"]["metadata"]["metaTitle"] == profile.name
    assert content["data"]["profile"]["metadata"]["metaOgImage"]["url"].startswith("http") is True


def test_owner_can_change_profile(django_user_client, graphql_user_client):
    response = graphql_user_client(
        query="""
            query Profile($id: ID!) {
                profile(id: $id) {
                    canChange: hasPerm(perm: "change")
                    canDelete: hasPerm(perm: "delete")
                    canChangeFull: hasPerm(perm: "baseapp_profiles.change_profile")
                    canDeleteFull: hasPerm(perm: "baseapp_profiles.delete_profile")
                }
            }
        """,
        variables={"id": django_user_client.user.profile.relay_id},
    )

    content = response.json()

    assert content["data"]["profile"]["canChange"]
    assert content["data"]["profile"]["canDelete"]
    assert content["data"]["profile"]["canChangeFull"]
    assert content["data"]["profile"]["canDeleteFull"]


def test_another_user_cant_change_profile(graphql_user_client):
    profile = ProfileFactory()

    response = graphql_user_client(
        query="""
            query Profile($id: ID!) {
                profile(id: $id) {
                    canChange: hasPerm(perm: "change")
                    canDelete: hasPerm(perm: "delete")
                    canChangeFull: hasPerm(perm: "baseapp_profiles.change_profile")
                    canDeleteFull: hasPerm(perm: "baseapp_profiles.delete_profile")
                }
            }
        """,
        variables={"id": profile.relay_id},
    )

    content = response.json()

    assert not content["data"]["profile"]["canChange"]
    assert not content["data"]["profile"]["canDelete"]
    assert not content["data"]["profile"]["canChangeFull"]
    assert not content["data"]["profile"]["canDeleteFull"]
