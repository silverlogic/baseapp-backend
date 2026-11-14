import pytest
import swapper
from django.contrib.auth.models import AnonymousUser

from baseapp_core.tests.factories import UserFactory

from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
profile_perm = Profile._meta.app_label
role_perm = ProfileUserRole._meta.app_label


@pytest.fixture
def ownerless() -> "Profile":
    return ProfileFactory(owner=None, status=Profile.ProfileStatus.PRIVATE)


def test_a_profile_can_have_no_owner(ownerless) -> None:
    assert ownerless.owner_id is None
    assert ownerless.is_owned_by(UserFactory()) is False
    assert ownerless.is_owned_by(AnonymousUser()) is False


def test_the_owner_owns_their_profile() -> None:
    profile = ProfileFactory()
    assert profile.is_owned_by(profile.owner)
    assert not profile.is_owned_by(UserFactory())


@pytest.mark.parametrize("perm", ["use_profile", "view_profile", "view_profile_members"])
def test_an_anonymous_user_gets_nothing_from_an_ownerless_profile(ownerless, perm) -> None:
    # Both ids are None: a bare `owner_id == user.id` would have read as ownership.
    assert not AnonymousUser().has_perm(f"{profile_perm}.{perm}", ownerless)
    assert not ownerless.check_if_member(AnonymousUser())


def test_a_signed_in_stranger_gets_nothing_either(ownerless) -> None:
    stranger = UserFactory()
    assert not stranger.has_perm(f"{profile_perm}.use_profile", ownerless)
    assert not stranger.has_perm(f"{role_perm}.add_profileuserrole", ownerless)
    assert not stranger.has_perm(f"{profile_perm}.change_profile", ownerless)


def test_active_admins_run_an_ownerless_profile(ownerless) -> None:
    admin = ProfileUserRoleFactory(profile=ownerless, role=ProfileUserRole.ProfileRoles.ADMIN)
    manager = ProfileUserRoleFactory(profile=ownerless, role=ProfileUserRole.ProfileRoles.MANAGER)

    for perm in ("add_profileuserrole", "change_profileuserrole", "delete_profileuserrole"):
        assert admin.user.has_perm(f"{role_perm}.{perm}", ownerless)
        assert not manager.user.has_perm(f"{role_perm}.{perm}", ownerless)
    assert manager.user.has_perm(f"{profile_perm}.use_profile", ownerless)
    assert manager.user.has_perm(f"{profile_perm}.view_profile_members", ownerless)


@pytest.mark.parametrize("perm", ["change_profile", "delete_profile"])
def test_active_admins_stand_in_for_the_owner(ownerless, perm) -> None:
    admin = ProfileUserRoleFactory(profile=ownerless, role=ProfileUserRole.ProfileRoles.ADMIN)
    manager = ProfileUserRoleFactory(profile=ownerless, role=ProfileUserRole.ProfileRoles.MANAGER)
    deactivated = ProfileUserRoleFactory(
        profile=ownerless,
        role=ProfileUserRole.ProfileRoles.ADMIN,
        status=ProfileUserRole.ProfileRoleStatus.INACTIVE,
    )

    assert admin.user.has_perm(f"{profile_perm}.{perm}", ownerless)
    assert not manager.user.has_perm(f"{profile_perm}.{perm}", ownerless)
    assert not deactivated.user.has_perm(f"{profile_perm}.{perm}", ownerless)


@pytest.mark.parametrize("perm", ["change_profile", "delete_profile"])
def test_admins_of_an_owned_profile_still_cannot_change_it(perm) -> None:
    profile = ProfileFactory()
    admin = ProfileUserRoleFactory(profile=profile, role=ProfileUserRole.ProfileRoles.ADMIN)

    assert not admin.user.has_perm(f"{profile_perm}.{perm}", profile)


PROFILE_UPDATE_GRAPHQL = """
    mutation ProfileUpdateMutation($input: ProfileUpdateInput!) {
        profileUpdate(input: $input) {
            profile { id name }
            errors { field messages }
        }
    }
"""

ALL_PROFILES_GRAPHQL = """
    query AllProfiles {
        allProfiles { edges { node { id } } }
    }
"""


def test_an_admin_renames_an_ownerless_profile(django_user_client, graphql_user_client) -> None:
    ownerless = ProfileFactory(owner=None, name="Old name")
    ProfileUserRoleFactory(
        profile=ownerless, user=django_user_client.user, role=ProfileUserRole.ProfileRoles.ADMIN
    )

    response = graphql_user_client(
        PROFILE_UPDATE_GRAPHQL,
        variables={"input": {"id": ownerless.relay_id, "name": "New name"}},
    )

    content = response.json()
    assert "errors" not in content, content
    ownerless.refresh_from_db()
    assert ownerless.name == "New name"


def test_members_see_their_private_ownerless_profile(
    ownerless, django_user_client, graphql_user_client
) -> None:
    ProfileUserRoleFactory(
        profile=ownerless, user=django_user_client.user, role=ProfileUserRole.ProfileRoles.MANAGER
    )
    hidden = ProfileFactory(owner=None, status=Profile.ProfileStatus.PRIVATE)
    ProfileUserRoleFactory(
        profile=hidden,
        user=django_user_client.user,
        status=ProfileUserRole.ProfileRoleStatus.PENDING,
    )

    response = graphql_user_client(ALL_PROFILES_GRAPHQL)

    ids = {edge["node"]["id"] for edge in response.json()["data"]["allProfiles"]["edges"]}
    assert ownerless.relay_id in ids
    # An invitation is not a membership.
    assert hidden.relay_id not in ids
