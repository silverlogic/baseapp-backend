"""`<profile app>.override_last_admin`: who may leave a profile without an active admin."""

import pytest
import swapper
from django.contrib.auth.models import Permission

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.exceptions import ProfileMembershipError
from baseapp_profiles.permissions import can_override_last_admin
from baseapp_profiles.services import members as member_service

from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
ADMIN = ProfileUserRole.ProfileRoles.ADMIN
MANAGER = ProfileUserRole.ProfileRoles.MANAGER
Status = ProfileUserRole.ProfileRoleStatus

DEACTIVATE = """
    mutation Deactivate($input: ProfileMemberDeactivateInput!) {
        profileMemberDeactivate(input: $input) { profileUserRole { status } }
    }
"""
UPDATE = """
    mutation Update($input: ProfileUserRoleUpdateInput!) {
        profileUserRoleUpdate(input: $input) { profileUserRole { role } }
    }
"""
DELETE = """
    mutation Delete($input: ProfileUserRoleDeleteInput!) {
        profileUserRoleDelete(input: $input) { deletedId }
    }
"""


def grant_override(user) -> None:
    user.user_permissions.add(
        Permission.objects.get(
            codename="override_last_admin", content_type__app_label=Profile._meta.app_label
        )
    )


@pytest.fixture
def last_admin() -> "ProfileUserRole":
    """The only admin of an ownerless profile."""
    return ProfileUserRoleFactory(profile=ProfileFactory(owner=None), role=ADMIN)


def test_the_service_override(last_admin) -> None:
    with pytest.raises(ProfileMembershipError):
        member_service.update_member(last_admin, role=MANAGER)

    member_service.update_member(last_admin, role=MANAGER, allow_last_admin=True)

    last_admin.refresh_from_db()
    assert last_admin.role == MANAGER


def test_nobody_but_superusers_holds_it_by_default(last_admin) -> None:
    assert not can_override_last_admin(last_admin.user, last_admin.profile)
    assert not can_override_last_admin(UserFactory(), last_admin.profile)
    assert can_override_last_admin(UserFactory(is_superuser=True), last_admin.profile)


def test_a_user_granted_the_permission_holds_it(last_admin) -> None:
    staff = UserFactory()
    grant_override(staff)

    assert can_override_last_admin(staff, last_admin.profile)


def test_the_last_admin_cannot_leave_without_it(last_admin, django_client, graphql_client) -> None:
    django_client.force_login(last_admin.user)
    ids = {"profileId": last_admin.profile.relay_id, "userId": last_admin.user.relay_id}

    for query, variables in (
        (DEACTIVATE, ids),
        (UPDATE, {**ids, "roleType": "MANAGER"}),
        (DELETE, ids),
    ):
        content = graphql_client(query, variables={"input": variables}).json()
        assert content["errors"][0]["extensions"]["code"] == "last_admin"


@pytest.mark.parametrize(
    "query,variables,expected",
    [
        (UPDATE, {"roleType": "MANAGER"}, (MANAGER, Status.ACTIVE)),
        (DEACTIVATE, {}, (ADMIN, Status.INACTIVE)),
        (DELETE, {}, None),
    ],
)
def test_holders_of_the_permission_may_override(
    last_admin, django_client, graphql_client, query, variables, expected
) -> None:
    # The admin also holds the override (granted to them directly here; a project would
    # usually grant it to support staff through its permission backend or a group).
    grant_override(last_admin.user)
    django_client.force_login(last_admin.user)
    ids = {"profileId": last_admin.profile.relay_id, "userId": last_admin.user.relay_id}

    content = graphql_client(query, variables={"input": {**ids, **variables}}).json()

    assert "errors" not in content, content
    row = ProfileUserRole.objects.filter(pk=last_admin.pk).first()
    assert (None if row is None else (row.role, row.status)) == expected
