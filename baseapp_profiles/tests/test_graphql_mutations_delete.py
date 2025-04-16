import pytest
import swapper
from django.contrib.auth.models import Permission

from .factories import ProfileFactory

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")


PROFILE_DELETE_GRAPHQL = """
    mutation ProfileDeleteMutation($input: ProfileDeleteInput!) {
        profileDelete(input: $input) {
            deletedId
            errors {
                field
                messages
            }
        }
    }
"""


def test_anon_cant_delete_profile(graphql_client):
    profile = ProfileFactory()

    response = graphql_client(
        PROFILE_DELETE_GRAPHQL,
        variables={"input": {"id": profile.relay_id}},
    )
    content = response.json()
    assert content["errors"][0]["message"] == "authentication required"


def test_user_cant_delete_any_profile(graphql_user_client):
    profile = ProfileFactory()

    response = graphql_user_client(
        PROFILE_DELETE_GRAPHQL,
        variables={"input": {"id": profile.relay_id}},
    )
    content = response.json()
    assert content["errors"][0]["extensions"]["code"] == "permission_required"


def test_owner_can_delete_profile(django_user_client, graphql_user_client):
    profile = ProfileFactory(owner=django_user_client.user)

    response = graphql_user_client(
        PROFILE_DELETE_GRAPHQL,
        variables={"input": {"id": profile.relay_id}},
    )
    content = response.json()
    assert content["data"]["profileDelete"]["deletedId"] == profile.relay_id
    with pytest.raises(Profile.DoesNotExist):
        profile.refresh_from_db()


def test_superuser_can_delete_profile(django_user_client, graphql_user_client):
    django_user_client.user.is_superuser = True
    django_user_client.user.save()

    profile = ProfileFactory()

    response = graphql_user_client(
        PROFILE_DELETE_GRAPHQL,
        variables={"input": {"id": profile.relay_id}},
    )
    content = response.json()
    assert content["data"]["profileDelete"]["deletedId"] == profile.relay_id
    with pytest.raises(Profile.DoesNotExist):
        profile.refresh_from_db()


def test_user_with_permission_can_delete_profile(django_user_client, graphql_user_client):
    perm = Permission.objects.get(
        content_type__app_label=Profile._meta.app_label, codename="delete_profile"
    )
    django_user_client.user.user_permissions.add(perm)

    profile = ProfileFactory()

    response = graphql_user_client(
        PROFILE_DELETE_GRAPHQL,
        variables={"input": {"id": profile.relay_id}},
    )
    content = response.json()
    assert content["data"]["profileDelete"]["deletedId"] == profile.relay_id
    with pytest.raises(Profile.DoesNotExist):
        profile.refresh_from_db()
