"""`<profile app>.view_profile_invitations`: who sees a profile's invitations."""

import pytest
import swapper
from django.core.exceptions import PermissionDenied

from baseapp_core.tests.factories import UserFactory
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
