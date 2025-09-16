import pytest
import swapper
from django.contrib.auth.models import Permission

from baseapp_core.tests.factories import UserFactory
from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")


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

PROFILE_USER_ROLE_DELETE_GRAPHQL = """
mutation ProfileUserRoleDeleteMutation($input: ProfileUserRoleDeleteInput!) {
    profileUserRoleDelete(input: $input) {
        deletedId
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

def test_user_profile_owner_can_remove_profile_member(django_user_client, graphql_user_client):
    perm = Permission.objects.get(
        content_type__app_label=ProfileUserRole._meta.app_label, codename="delete_profileuserrole"
    )

    user = django_user_client.user
    user_2 = UserFactory()

    user.user_permissions.add(perm)
    profile = ProfileFactory(owner=user)
    profile_user_role = ProfileUserRoleFactory(
        profile=profile, user=user_2, role=ProfileUserRole.ProfileRoles.MANAGER
    )

    response = graphql_user_client(
        PROFILE_USER_ROLE_DELETE_GRAPHQL,
        variables={"input": {"userId": user_2.relay_id, "profileId": profile.relay_id}},
    )
    content = response.json()

    assert content["data"]["profileUserRoleDelete"]["deletedId"] == profile_user_role.relay_id
    assert not ProfileUserRole.objects.filter(id=profile_user_role.id).exists()


def test_user_with_permission_can_remove_profile_member(django_user_client, graphql_user_client):
    perm = Permission.objects.get(
        content_type__app_label=ProfileUserRole._meta.app_label, codename="delete_profileuserrole"
    )

    user = django_user_client.user
    user.user_permissions.add(perm)
    user_2 = UserFactory()
    user_3 = UserFactory()

    profile = ProfileFactory(owner=user_2)
    ProfileUserRoleFactory(profile=profile, user=user, role=ProfileUserRole.ProfileRoles.ADMIN)
    profile_user_role = ProfileUserRoleFactory(
        profile=profile, user=user_3, role=ProfileUserRole.ProfileRoles.MANAGER
    )

    response = graphql_user_client(
        PROFILE_USER_ROLE_DELETE_GRAPHQL,
        variables={"input": {"userId": user_3.relay_id, "profileId": profile.relay_id}},
    )
    content = response.json()
    assert content["data"]["profileUserRoleDelete"]["deletedId"] == profile_user_role.relay_id
    assert not ProfileUserRole.objects.filter(id=profile_user_role.id).exists()


def test_user_without_permission_cant_remove_profile_member(
    django_user_client, graphql_user_client
):
    user = django_user_client.user
    user_2 = UserFactory()
    user_3 = UserFactory()

    profile = ProfileFactory(owner=user_2)
    ProfileUserRoleFactory(profile=profile, user=user, role=ProfileUserRole.ProfileRoles.MANAGER)
    profile_user_role = ProfileUserRoleFactory(
        profile=profile, user=user_3, role=ProfileUserRole.ProfileRoles.MANAGER
    )

    response = graphql_user_client(
        PROFILE_USER_ROLE_DELETE_GRAPHQL,
        variables={"input": {"userId": user_3.relay_id, "profileId": profile.relay_id}},
    )
    content = response.json()
    assert content["errors"][0]["extensions"]["code"] == "permission_required"
    assert ProfileUserRole.objects.filter(id=profile_user_role.id).exists()
