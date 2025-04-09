import pytest
import swapper
from django.contrib.auth.models import Permission
from django.test.client import MULTIPART_CONTENT

from baseapp_core.tests.factories import UserFactory
from baseapp_pages.tests.factories import URLPathFactory

from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")

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

PROFILE_ROLE_UPDATE_GRAPHQL = """
mutation ProfileRoleUpdateMutation($input: RoleUpdateInput!) {
    profileRoleUpdate(input: $input) {
        profileUserRole {
            id
            role
            status
        }
        errors {
            field
            messages
        }
    }
}
"""

PROFILE_MEMBER_REMOVE_GRAPHQL = """
mutation ProfileRemoveMemberMutation($input: ProfileRemoveMemberInput!) {
    profileRemoveMember(input: $input) {
        deletedId
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
    url_path = "existingpath"
    URLPathFactory(path=f"/{url_path}")
    profile = ProfileFactory(owner=django_user_client.user)

    response = graphql_user_client(
        PROFILE_UPDATE_GRAPHQL,
        variables={"input": {"id": profile.relay_id, "urlPath": url_path}},
    )
    content = response.json()
    print(content)
    assert (
        content["data"]["profileUpdate"]["errors"][0]["messages"][0]
        == "Username already in use, suggested username: /existingpath1"
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
        content_type__app_label=Profile._meta.app_label, codename="change_profile"
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


def test_user_profile_owner_can_update_role(django_user_client, graphql_user_client):

    perm = Permission.objects.get(
        content_type__app_label=ProfileUserRole._meta.app_label, codename="change_profileuserrole"
    )

    user = django_user_client.user
    user_2 = UserFactory()

    user.user_permissions.add(perm)
    profile = ProfileFactory(owner=user)
    ProfileUserRoleFactory(profile=profile, user=user_2, role=ProfileUserRole.ProfileRoles.MANAGER)

    response = graphql_user_client(
        PROFILE_ROLE_UPDATE_GRAPHQL,
        variables={
            "input": {"userId": user_2.relay_id, "profileId": profile.relay_id, "roleType": "ADMIN"}
        },
    )
    content = response.json()

    assert content["data"]["profileRoleUpdate"]["profileUserRole"]["role"] == "ADMIN"
    profile.refresh_from_db()


def test_user_with_permission_can_update_role(django_user_client, graphql_user_client):

    perm = Permission.objects.get(
        content_type__app_label=ProfileUserRole._meta.app_label, codename="change_profileuserrole"
    )

    user = django_user_client.user
    user.user_permissions.add(perm)
    user_2 = UserFactory()
    user_3 = UserFactory()

    profile = ProfileFactory(owner=user_2)
    ProfileUserRoleFactory(profile=profile, user=user, role=ProfileUserRole.ProfileRoles.ADMIN)
    ProfileUserRoleFactory(profile=profile, user=user_3, role=ProfileUserRole.ProfileRoles.MANAGER)

    response = graphql_user_client(
        PROFILE_ROLE_UPDATE_GRAPHQL,
        variables={
            "input": {"userId": user_3.relay_id, "profileId": profile.relay_id, "roleType": "ADMIN"}
        },
    )
    content = response.json()

    assert content["data"]["profileRoleUpdate"]["profileUserRole"]["role"] == "ADMIN"
    profile.refresh_from_db()


def test_user_without_permission_cant_update_role(django_user_client, graphql_user_client):

    perm = Permission.objects.get(
        content_type__app_label=ProfileUserRole._meta.app_label, codename="change_profileuserrole"
    )

    user = django_user_client.user
    user.user_permissions.add(perm)
    user_2 = UserFactory()
    user_3 = UserFactory()

    profile = ProfileFactory(owner=user_2)
    ProfileUserRoleFactory(profile=profile, user=user, role=ProfileUserRole.ProfileRoles.MANAGER)
    ProfileUserRoleFactory(profile=profile, user=user_3, role=ProfileUserRole.ProfileRoles.MANAGER)

    response = graphql_user_client(
        PROFILE_ROLE_UPDATE_GRAPHQL,
        variables={
            "input": {"userId": user_3.relay_id, "profileId": profile.relay_id, "roleType": "ADMIN"}
        },
    )
    content = response.json()
    assert content["errors"][0]["message"] == "You don't have permission to perform this action"
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
        PROFILE_MEMBER_REMOVE_GRAPHQL,
        variables={"input": {"userId": user_2.relay_id, "profileId": profile.relay_id}},
    )
    content = response.json()

    assert content["data"]["profileRemoveMember"]["deletedId"] == profile_user_role.relay_id
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
        PROFILE_MEMBER_REMOVE_GRAPHQL,
        variables={"input": {"userId": user_3.relay_id, "profileId": profile.relay_id}},
    )
    content = response.json()
    assert content["data"]["profileRemoveMember"]["deletedId"] == profile_user_role.relay_id
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
        PROFILE_MEMBER_REMOVE_GRAPHQL,
        variables={"input": {"userId": user_3.relay_id, "profileId": profile.relay_id}},
    )
    content = response.json()
    assert content["errors"][0]["extensions"]["code"] == "permission_required"
    assert ProfileUserRole.objects.filter(id=profile_user_role.id).exists()
