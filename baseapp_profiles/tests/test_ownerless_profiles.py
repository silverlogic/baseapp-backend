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
