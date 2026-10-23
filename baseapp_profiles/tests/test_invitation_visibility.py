"""`<profile app>.view_profile_invitations`: who sees a profile's invitations."""

import pytest
import swapper
from django.core.exceptions import PermissionDenied
from rest_framework.test import APIClient

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.permissions import ProfilesPermissionsBackend, is_active_member
from baseapp_profiles.services import invitations as invitation_service

from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
ADMIN = ProfileUserRole.ProfileRoles.ADMIN
Status = ProfileUserRole.ProfileRoleStatus


class AdminsSeeInvitationsBackend:
    """A project rule: only a profile's admins see its invitations."""

    def authenticate(self, request, **credentials) -> None:
        return None

    def has_perm(self, user_obj, perm, obj=None) -> bool:
        if perm == f"{Profile._meta.app_label}.view_profile_invitations" and obj is not None:
            if not obj.members.filter(
                user_id=user_obj.pk, role=ADMIN, status=Status.ACTIVE
            ).exists():
                raise PermissionDenied
        return False


class NarrowedProfilesPermissionsBackend(ProfilesPermissionsBackend):
    """The README's way to narrow the permission: override `has_invitation_perm`."""

    def has_invitation_perm(self, user_obj, perm, obj) -> bool:
        if perm.endswith(".view_profile_invitations"):
            return (
                obj.is_owned_by(user_obj)
                or is_active_member(obj, user_obj, role=ADMIN)
                or user_obj.has_perm(perm)
            )
        return super().has_invitation_perm(user_obj, perm, obj)


MEMBERS = """
    query Members($id: ID!) {
        profile(id: $id) {
            members { edges { node { id status invitedEmail } } }
        }
    }
"""
NODE = """
    query Node($id: ID!) {
        node(id: $id) { ... on ProfileUserRole { id } }
    }
"""


@pytest.fixture
def profile() -> "Profile":
    profile = ProfileFactory(owner=None, status=Profile.ProfileStatus.PUBLIC)
    ProfileUserRoleFactory(profile=profile, role=ADMIN, user=UserFactory(email="ad@x.com"))
    ProfileUserRoleFactory(profile=profile, status=Status.INACTIVE)
    invitation_service.send_invitations(profile, ["ann@example.com"])
    return profile


@pytest.fixture
def manager(profile) -> "ProfileUserRole":
    return ProfileUserRoleFactory(profile=profile, user=UserFactory(email="mgr@x.com"))


@pytest.fixture
def admins_only(settings) -> None:
    settings.AUTHENTICATION_BACKENDS = [
        "baseapp_profiles.tests.test_invitation_visibility.AdminsSeeInvitationsBackend",
        *settings.AUTHENTICATION_BACKENDS,
    ]


def statuses(content: dict) -> list[tuple[str, str | None]]:
    edges = content["data"]["profile"]["members"]["edges"]
    return sorted((edge["node"]["status"], edge["node"]["invitedEmail"]) for edge in edges)


def test_members_see_invitations_by_default(profile, manager, django_client, graphql_client):
    django_client.force_login(manager.user)

    content = graphql_client(MEMBERS, variables={"id": profile.relay_id}).json()

    assert ("PENDING", "ann@example.com") in statuses(content)


def test_without_the_permission_only_members_are_listed(
    profile, manager, admins_only, django_client, graphql_client
) -> None:
    django_client.force_login(manager.user)

    content = graphql_client(MEMBERS, variables={"id": profile.relay_id}).json()

    assert statuses(content) == [("ACTIVE", None), ("ACTIVE", None), ("INACTIVE", None)]


def test_with_the_permission_everything_is_listed(
    profile, admins_only, django_client, graphql_client
) -> None:
    admin = profile.members.get(role=ADMIN)
    django_client.force_login(admin.user)

    content = graphql_client(MEMBERS, variables={"id": profile.relay_id}).json()

    assert ("PENDING", "ann@example.com") in statuses(content)


def test_a_pending_row_is_hidden_from_node_without_the_permission(
    profile, manager, admins_only, django_client, graphql_client
) -> None:
    pending = profile.members.get(status=Status.PENDING)
    django_client.force_login(manager.user)

    content = graphql_client(NODE, variables={"id": pending.relay_id}).json()
    assert content["data"]["node"] is None

    content = graphql_client(NODE, variables={"id": manager.relay_id}).json()
    assert content["data"]["node"] == {"id": manager.relay_id}


# --- REST ----------------------------------------------------------------------------------

INVITATIONS = "/v1/profile-invitations"


def rest_client(user, profile) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    client.credentials(HTTP_CURRENT_PROFILE=profile.relay_id)
    return client


def test_rest_invitations_are_listed_for_members_by_default(profile, manager) -> None:
    pending = profile.members.get(status=Status.PENDING)
    client = rest_client(manager.user, profile)

    assert client.get(INVITATIONS).status_code == 200
    assert client.get(f"{INVITATIONS}/{pending.pk}").status_code == 200


def test_rest_invitations_need_the_permission(profile, manager, admins_only) -> None:
    pending = profile.members.get(status=Status.PENDING)
    client = rest_client(manager.user, profile)

    listed = client.get(INVITATIONS)
    retrieved = client.get(f"{INVITATIONS}/{pending.pk}")

    assert (listed.status_code, retrieved.status_code) == (403, 403)
    assert "ann@example.com" not in listed.content.decode()
    admin = profile.members.get(role=ADMIN)
    assert rest_client(admin.user, profile).get(INVITATIONS).status_code == 200


def test_a_backend_subclass_narrows_the_permission(profile, manager, settings) -> None:
    settings.AUTHENTICATION_BACKENDS = [
        "baseapp_profiles.tests.test_invitation_visibility.NarrowedProfilesPermissionsBackend"
        if backend == "baseapp_profiles.permissions.ProfilesPermissionsBackend"
        else backend
        for backend in settings.AUTHENTICATION_BACKENDS
    ]
    admin = profile.members.get(role=ADMIN)
    perm = f"{Profile._meta.app_label}.view_profile_invitations"

    assert not manager.user.has_perm(perm, profile)
    assert admin.user.has_perm(perm, profile)
    assert rest_client(manager.user, profile).get(INVITATIONS).status_code == 403
