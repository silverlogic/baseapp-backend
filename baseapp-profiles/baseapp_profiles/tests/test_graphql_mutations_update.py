import pytest
import swapper
from baseapp_pages.tests.factories import URLPathFactory
from django.contrib.auth.models import Permission
from django.test.client import MULTIPART_CONTENT

from .factories import ProfileFactory

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")

PROFILE_UPDATE_GRAPHQL = """
    mutation ProfileUpdateMutation($input: ProfileUpdateInput!) {
        profileUpdate(input: $input) {
            profile {
                id
                name
                biography
                image(width: 100, height: 100) {
                    url
                }
                bannerImage(width: 100, height: 100) {
                    url
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""


def test_anon_cant_update_profile(graphql_client):
    profile = ProfileFactory()
    old_biography = profile.biography

    response = graphql_client(
        PROFILE_UPDATE_GRAPHQL,
        variables={"input": {"id": profile.relay_id, "biography": "my edited profile"}},
    )
    content = response.json()
    assert content["errors"][0]["message"] == "authentication required"
    profile.refresh_from_db()
    assert profile.biography == old_biography


def test_user_cant_update_any_profile(graphql_user_client):
    profile = ProfileFactory()
    old_biography = profile.biography

    response = graphql_user_client(
        PROFILE_UPDATE_GRAPHQL,
        variables={"input": {"id": profile.relay_id, "biography": "my edited profile"}},
    )
    content = response.json()
    assert content["errors"][0]["extensions"]["code"] == "permission_required"
    profile.refresh_from_db()
    assert profile.biography == old_biography


def test_owner_can_update_profile(django_user_client, graphql_user_client):
    profile = ProfileFactory(owner=django_user_client.user)
    new_biography = "my edited profile"

    response = graphql_user_client(
        PROFILE_UPDATE_GRAPHQL,
        variables={"input": {"id": profile.relay_id, "biography": new_biography}},
    )
    content = response.json()
    assert content["data"]["profileUpdate"]["profile"]["biography"] == new_biography
    profile.refresh_from_db()
    assert profile.biography == new_biography


def test_owner_can_update_profile_url_path(django_user_client, graphql_user_client):
    profile = ProfileFactory(owner=django_user_client.user)
    graphql_user_client(
        PROFILE_UPDATE_GRAPHQL,
        variables={"input": {"id": profile.relay_id, "urlPath": "new-path"}},
    )
    assert profile.url_paths.all().count() == 1


def test_owner_can_update_profile_url_path_already_in_use(django_user_client, graphql_user_client):
    url_path = "new-path"
    URLPathFactory(path=url_path)
    profile = ProfileFactory(owner=django_user_client.user)

    response = graphql_user_client(
        PROFILE_UPDATE_GRAPHQL,
        variables={"input": {"id": profile.relay_id, "urlPath": url_path}},
    )
    content = response.json()
    assert (
        content["data"]["profileUpdate"]["errors"][0]["messages"][0]
        == "URL path already in use, please choose another one"
    )


def test_owner_can_update_profile_image(django_user_client, graphql_user_client, image_djangofile):
    profile = ProfileFactory(owner=django_user_client.user)
    response = graphql_user_client(
        PROFILE_UPDATE_GRAPHQL,
        variables={"input": {"id": profile.relay_id}},
        content_type=MULTIPART_CONTENT,
        extra={"image": image_djangofile},
    )

    content = response.json()
    assert content["data"]["profileUpdate"]["profile"]["image"]["url"].startswith("http")


def test_owner_can_update_profile_banner_image(
    django_user_client, graphql_user_client, image_djangofile
):
    profile = ProfileFactory(owner=django_user_client.user)
    response = graphql_user_client(
        PROFILE_UPDATE_GRAPHQL,
        variables={"input": {"id": profile.relay_id}},
        content_type=MULTIPART_CONTENT,
        extra={"banner_image": image_djangofile},
    )

    content = response.json()
    assert content["data"]["profileUpdate"]["profile"]["bannerImage"]["url"].startswith("http://")


def test_owner_can_delete_profile_image(django_user_client, graphql_user_client):
    profile = ProfileFactory(owner=django_user_client.user)
    response = graphql_user_client(
        PROFILE_UPDATE_GRAPHQL,
        variables={"input": {"id": profile.relay_id, "image": None}},
    )

    content = response.json()
    assert content["data"]["profileUpdate"]["profile"]["image"] is None


def test_owner_can_delete_profile_banner_image(django_user_client, graphql_user_client):
    profile = ProfileFactory(owner=django_user_client.user)
    response = graphql_user_client(
        PROFILE_UPDATE_GRAPHQL,
        variables={"input": {"id": profile.relay_id, "bannerImage": None}},
    )

    content = response.json()
    assert content["data"]["profileUpdate"]["profile"]["bannerImage"] is None


def test_owner_can_update_profile_banner_image_camel_case(
    django_user_client, graphql_user_client, image_djangofile
):
    profile = ProfileFactory(owner=django_user_client.user)
    response = graphql_user_client(
        PROFILE_UPDATE_GRAPHQL,
        variables={"input": {"id": profile.relay_id}},
        content_type=MULTIPART_CONTENT,
        extra={"bannerImage": image_djangofile},
    )

    content = response.json()
    assert content["data"]["profileUpdate"]["profile"]["bannerImage"]["url"].startswith("http://")


def test_superuser_can_update_profile(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()
    new_biography = "my edited profile"

    profile = ProfileFactory()

    response = graphql_user_client(
        PROFILE_UPDATE_GRAPHQL,
        variables={"input": {"id": profile.relay_id, "biography": new_biography}},
    )
    content = response.json()
    assert content["data"]["profileUpdate"]["profile"]["biography"] == new_biography
    profile.refresh_from_db()
    assert profile.biography == new_biography


def test_user_with_permission_can_update_profile(django_user_client, graphql_user_client):
    perm = Permission.objects.get(
        content_type__app_label="baseapp_profiles", codename="change_profile"
    )
    django_user_client.user.user_permissions.add(perm)
    new_biography = "my edited profile"

    profile = ProfileFactory()

    response = graphql_user_client(
        PROFILE_UPDATE_GRAPHQL,
        variables={"input": {"id": profile.relay_id, "biography": new_biography}},
    )
    content = response.json()
    assert content["data"]["profileUpdate"]["profile"]["biography"] == new_biography
    profile.refresh_from_db()
    assert profile.biography == new_biography
