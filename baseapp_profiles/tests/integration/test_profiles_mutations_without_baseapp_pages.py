import pytest
import swapper
from django.contrib.auth.models import Permission

from baseapp_core.graphql import get_pk_from_relay_id
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")

PROFILE_CREATE_GRAPHQL = """
    mutation ProfileCreateMutation($input: ProfileCreateInput!) {
        profileCreate(input: $input) {
            profile {
                node {
                    id
                    name
                }
            }
            errors {
                field
                messages
            }
        }
    }
"""

PROFILE_UPDATE_GRAPHQL = """
    mutation ProfileUpdateMutation($input: ProfileUpdateInput!) {
        profileUpdate(input: $input) {
            profile {
                id
                name
                biography
            }
            errors {
                field
                messages
            }
        }
    }
"""


@pytest.mark.parametrize("with_disabled_apps", [["baseapp_pages"]], indirect=True)
class TestProfilesMutationsWithoutBaseappPages:
    def test_profile_create_succeeds_and_skips_url_path_when_baseapp_pages_disabled(
        self,
        with_disabled_apps,
        django_user_client,
        graphql_user_client,
    ) -> None:
        perm = Permission.objects.get(
            content_type__app_label=Profile._meta.app_label,
            codename="add_profile",
        )
        django_user_client.user.user_permissions.add(perm)

        response = graphql_user_client(
            PROFILE_CREATE_GRAPHQL,
            variables={
                "input": {
                    "name": "Profile Without Pages",
                    "urlPath": "unusedslug12",
                }
            },
        )
        content = response.json()
        assert "errors" not in content
        payload = content["data"]["profileCreate"]
        assert payload["errors"] is None

        node_id = payload["profile"]["node"]["id"]
        profile = Profile.objects.get(pk=get_pk_from_relay_id(node_id))
        assert profile.name == "Profile Without Pages"
        assert profile.owner_id == django_user_client.user.pk
        assert profile.url_paths.count() == 0

    def test_profile_update_applies_fields_and_skips_url_path_when_baseapp_pages_disabled(
        self,
        with_disabled_apps,
        django_user_client,
        graphql_user_client,
    ) -> None:
        profile = ProfileFactory(owner=django_user_client.user, biography="before")
        assert profile.url_paths.count() == 0

        response = graphql_user_client(
            PROFILE_UPDATE_GRAPHQL,
            variables={
                "input": {
                    "id": profile.relay_id,
                    "biography": "after",
                    "urlPath": "ignoredslug1",
                }
            },
        )
        content = response.json()
        assert "errors" not in content
        payload = content["data"]["profileUpdate"]
        assert payload["errors"] is None
        assert payload["profile"]["biography"] == "after"

        profile.refresh_from_db()
        assert profile.biography == "after"
        assert profile.url_paths.count() == 0
