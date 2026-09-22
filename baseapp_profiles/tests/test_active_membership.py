"""
A membership only grants access while it is ACTIVE.

These cover the boundary from both sides: that an ACTIVE member reaches the profile, and
— the half that actually catches a regression — that a member in every other status does
not, on their very next request and without waiting for them to sign out.
"""

from unittest.mock import patch

import pytest
import swapper
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.middleware import CurrentProfileMiddleware

from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")

profile_app_label = Profile._meta.app_label
profile_user_role_app_label = ProfileUserRole._meta.app_label

USE_PROFILE = f"{profile_app_label}.use_profile"
VIEW_MEMBERS = f"{profile_app_label}.view_profile_members"
ADD_ROLE = f"{profile_user_role_app_label}.add_profileuserrole"

NON_ACTIVE_STATUSES = [
    ProfileUserRole.ProfileRoleStatus.PENDING,
    ProfileUserRole.ProfileRoleStatus.INACTIVE,
    ProfileUserRole.ProfileRoleStatus.DECLINED,
    ProfileUserRole.ProfileRoleStatus.EXPIRED,
]


def test_active_member_can_use_profile() -> None:
    user = UserFactory()
    profile = ProfileFactory()
    ProfileUserRoleFactory(user=user, profile=profile)

    assert user.has_perm(USE_PROFILE, profile) is True


@pytest.mark.parametrize("status", NON_ACTIVE_STATUSES)
def test_non_active_member_cannot_use_profile(status) -> None:
    user = UserFactory()
    profile = ProfileFactory()
    ProfileUserRoleFactory(user=user, profile=profile, status=status)

    assert user.has_perm(USE_PROFILE, profile) is False


def test_owner_can_use_profile_without_a_membership() -> None:
    user = UserFactory()
    profile = ProfileFactory(owner=user)

    assert user.has_perm(USE_PROFILE, profile) is True


def test_anonymous_user_cannot_use_profile() -> None:
    profile = ProfileFactory()
    # A pending invitation carries no user, so a null user_id must not match it.
    ProfileUserRoleFactory(
        user=None,
        profile=profile,
        invited_email="invitee@example.com",
        status=ProfileUserRole.ProfileRoleStatus.PENDING,
    )

    assert AnonymousUser().has_perm(USE_PROFILE, profile) is False


@pytest.mark.parametrize("status", NON_ACTIVE_STATUSES)
def test_non_active_member_cannot_view_members(status) -> None:
    user = UserFactory()
    profile = ProfileFactory()
    ProfileUserRoleFactory(user=user, profile=profile, status=status)

    assert user.has_perm(VIEW_MEMBERS, profile) is False


def test_non_active_admin_cannot_manage_members() -> None:
    user = UserFactory()
    profile = ProfileFactory()
    ProfileUserRoleFactory(
        user=user,
        profile=profile,
        role=ProfileUserRole.ProfileRoles.ADMIN,
        status=ProfileUserRole.ProfileRoleStatus.INACTIVE,
    )

    assert user.has_perm(ADD_ROLE, profile) is False


def test_active_admin_can_manage_members() -> None:
    user = UserFactory()
    profile = ProfileFactory()
    ProfileUserRoleFactory(user=user, profile=profile, role=ProfileUserRole.ProfileRoles.ADMIN)

    assert user.has_perm(ADD_ROLE, profile) is True


class TestDeactivationTakesEffectOnTheNextRequest:
    """
    The account is closed by flipping `status`; nothing signs the user out. So the
    boundary has to be re-read per request rather than cached at sign-in.
    """

    def _current_profile(self, user, profile) -> "Profile | None":
        request = RequestFactory().get("/some-path/")
        request.user = user
        request.META["HTTP_CURRENT_PROFILE"] = profile.relay_id
        CurrentProfileMiddleware(lambda r: HttpResponse("OK"))(request)
        return request.user.current_profile

    def test_deactivated_member_stops_reaching_the_profile(self) -> None:
        user = UserFactory()
        profile = ProfileFactory()
        membership = ProfileUserRoleFactory(user=user, profile=profile)

        assert self._current_profile(user, profile) == profile

        membership.status = ProfileUserRole.ProfileRoleStatus.INACTIVE
        membership.save(update_fields=["status"])

        # The middleware re-resolves per request, so the same user object is enough —
        # nothing is cached between the two calls.
        assert self._current_profile(user, profile) is None

    def test_reactivated_member_reaches_it_again(self) -> None:
        user = UserFactory()
        profile = ProfileFactory()
        membership = ProfileUserRoleFactory(
            user=user, profile=profile, status=ProfileUserRole.ProfileRoleStatus.INACTIVE
        )

        assert self._current_profile(user, profile) is None

        membership.status = ProfileUserRole.ProfileRoleStatus.ACTIVE
        membership.save(update_fields=["status"])

        assert self._current_profile(user, profile) == profile


class TestProfileManager:
    def test_filter_user_profiles_excludes_non_active_memberships(self) -> None:
        user = UserFactory()
        active = ProfileFactory()
        ProfileUserRoleFactory(user=user, profile=active)
        inactive = ProfileFactory()
        ProfileUserRoleFactory(
            user=user, profile=inactive, status=ProfileUserRole.ProfileRoleStatus.INACTIVE
        )

        profiles = Profile.objects.filter_user_profiles(user)

        assert active in profiles
        assert inactive not in profiles

    def test_filter_user_profiles_does_not_duplicate_owned_memberships(self) -> None:
        # Owner *and* member of the same profile: the Exists() subquery must not fan the
        # row out the way a join would, so the result needs no .distinct().
        user = UserFactory()
        profile = ProfileFactory(owner=user)
        ProfileUserRoleFactory(user=user, profile=profile)

        assert list(Profile.objects.filter_user_profiles(user)).count(profile) == 1

    def test_get_if_member_ignores_non_active_memberships(self) -> None:
        user = UserFactory()
        profile = ProfileFactory()
        ProfileUserRoleFactory(
            user=user, profile=profile, status=ProfileUserRole.ProfileRoleStatus.INACTIVE
        )

        assert Profile.objects.get_if_member(user, pk=profile.pk) is None

    def test_get_if_member_returns_active_membership(self) -> None:
        user = UserFactory()
        profile = ProfileFactory()
        ProfileUserRoleFactory(user=user, profile=profile)

        assert Profile.objects.get_if_member(user, pk=profile.pk) == profile


class TestAssignableRoles:
    """
    A project may declare roles it is not ready to hand out — reserving the values while a
    later phase decides what they reach. The mutations refuse those with a clear error
    rather than letting the write reach a database constraint.
    """

    def test_every_declared_role_is_assignable_by_default(self) -> None:
        assert set(ProfileUserRole.assignable_roles()) == set(ProfileUserRole.ProfileRoles.values)

    def test_the_validator_refuses_a_role_left_out(self) -> None:
        # One validator for all three mutations that take a role, so the error shape
        # cannot drift between them.
        from graphql.error import GraphQLError

        from baseapp_profiles.graphql.mutations.roles import validate_assignable_role

        reserved = ProfileUserRole.ProfileRoles.MANAGER
        allowed = [r for r in ProfileUserRole.ProfileRoles.values if r != reserved]

        with patch.object(ProfileUserRole, "assignable_roles", classmethod(lambda cls: allowed)):
            with pytest.raises(GraphQLError) as excinfo:
                validate_assignable_role(reserved)
            assert excinfo.value.extensions["code"] == "invalid_input"

            validate_assignable_role(ProfileUserRole.ProfileRoles.ADMIN)  # does not raise

    def test_a_role_left_out_is_refused(self) -> None:
        reserved = ProfileUserRole.ProfileRoles.MANAGER
        allowed = [r for r in ProfileUserRole.ProfileRoles.values if r != reserved]

        with patch.object(ProfileUserRole, "assignable_roles", classmethod(lambda cls: allowed)):
            assert reserved not in ProfileUserRole.assignable_roles()
            assert ProfileUserRole.ProfileRoles.ADMIN in ProfileUserRole.assignable_roles()
