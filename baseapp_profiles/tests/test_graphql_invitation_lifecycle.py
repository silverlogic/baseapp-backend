import pytest
import swapper
from django.contrib.auth import get_user_model

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.services import invitations as service

from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

User = get_user_model()
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
ADMIN = ProfileUserRole.ProfileRoles.ADMIN
MANAGER = ProfileUserRole.ProfileRoles.MANAGER
Status = ProfileUserRole.ProfileRoleStatus

SEND = """
    mutation Send($input: ProfileSendInvitationInput!) {
        profileSendInvitation(input: $input) {
            emailsSent
            emailsHeld
            profileUserRoles {
                id
                invitedEmail
                invitedFirstName
                invitedLastName
                message
                sentCount
                lastSentAt
                invitedBy { id }
            }
        }
    }
"""

PREVIEW = """
    query Preview($token: String!) {
        profileInvitationPreview(token: $token) {
            profileName
            invitedEmail
            role
            status
            expiresAt
        }
    }
"""

SIGNUP = """
    mutation Signup($input: ProfileAcceptInvitationWithSignupInput!) {
        profileAcceptInvitationWithSignup(input: $input) {
            success
            email
        }
    }
"""

CANCEL = """
    mutation Cancel($input: ProfileCancelInvitationInput!) {
        profileCancelInvitation(input: $input) {
            success
            profileUserRole { id status deactivatedAt }
        }
    }
"""

DEACTIVATE = """
    mutation Deactivate($input: ProfileMemberDeactivateInput!) {
        profileMemberDeactivate(input: $input) {
            profileUserRole { id status deactivatedAt }
        }
    }
"""

REACTIVATE = """
    mutation Reactivate($input: ProfileMemberReactivateInput!) {
        profileMemberReactivate(input: $input) {
            profileUserRole { id status deactivatedAt }
        }
    }
"""

UPDATE_ROLE = """
    mutation Update($input: ProfileUserRoleUpdateInput!) {
        profileUserRoleUpdate(input: $input) {
            profileUserRole { id role }
        }
    }
"""

DELETE_ROLE = """
    mutation Delete($input: ProfileUserRoleDeleteInput!) {
        profileUserRoleDelete(input: $input) {
            deletedId
        }
    }
"""


def error_code(content: dict) -> str:
    return content["errors"][0]["extensions"]["code"]


def test_send_takes_invitee_names_and_a_message(django_user_client, graphql_user_client) -> None:
    owner = django_user_client.user
    profile = ProfileFactory(owner=owner)

    content = graphql_user_client(
        SEND,
        variables={
            "input": {
                "profileId": profile.relay_id,
                "emails": ["plain@example.com"],
                "invitees": [{"email": "ann@example.com", "firstName": "Ann", "lastName": "Lee"}],
                "role": "MANAGER",
                "message": "Join us",
            }
        },
    ).json()

    assert "errors" not in content, content
    data = content["data"]["profileSendInvitation"]
    assert data["emailsSent"] == 2
    assert data["emailsHeld"] == 0
    ann = data["profileUserRoles"][1]
    assert (ann["invitedEmail"], ann["invitedFirstName"], ann["invitedLastName"]) == (
        "ann@example.com",
        "Ann",
        "Lee",
    )
    assert ann["message"] == "Join us"
    assert ann["sentCount"] == 1
    assert ann["lastSentAt"] is not None
    assert ann["invitedBy"]["id"] == owner.relay_id


def test_held_invitations_are_counted(django_user_client, graphql_user_client, settings) -> None:
    settings.BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK = lambda invitation: True
    profile = ProfileFactory(owner=django_user_client.user)

    content = graphql_user_client(
        SEND,
        variables={
            "input": {"profileId": profile.relay_id, "emails": ["a@x.com"], "role": "ADMIN"}
        },
    ).json()

    assert content["data"]["profileSendInvitation"]["emailsSent"] == 0
    assert content["data"]["profileSendInvitation"]["emailsHeld"] == 1


def test_invitation_details_are_hidden_from_non_members(graphql_client) -> None:
    # `profileInvitation(token)` hands the row to anyone holding the token; the invitation
    # details and audit fields stay members-only, like `invitedEmail` always was.
    invitation = service.send_invitations(
        ProfileFactory(), [{"email": "ann@example.com", "first_name": "Ann"}], message="Hi"
    ).invitations[0]

    content = graphql_client(
        """
        query Invitation($token: String!) {
            profileInvitation(token: $token) {
                status invitedEmail invitedFirstName message sentCount deactivatedAt
                invitedBy { id }
            }
        }
        """,
        variables={"token": invitation.invitation_token},
    ).json()

    assert content["data"]["profileInvitation"] == {
        "status": "PENDING",
        "invitedEmail": None,
        "invitedFirstName": None,
        "message": None,
        "sentCount": None,
        "deactivatedAt": None,
        "invitedBy": None,
    }


def test_preview_is_public_and_minimal(graphql_client) -> None:
    profile = ProfileFactory(name="Acme")
    invitation = service.send_invitations(profile, ["ann@example.com"], role=ADMIN).invitations[0]

    content = graphql_client(PREVIEW, variables={"token": invitation.invitation_token}).json()

    assert content["data"]["profileInvitationPreview"] == {
        "profileName": "Acme",
        "invitedEmail": "ann@example.com",
        "role": "ADMIN",
        "status": "PENDING",
        "expiresAt": invitation.invitation_expires_at.isoformat(),
    }
    content = graphql_client(PREVIEW, variables={"token": "unknown"}).json()
    assert content["data"]["profileInvitationPreview"] is None


class TestAcceptWithSignup:
    def test_is_refused_unless_enabled(self, graphql_client) -> None:
        invitation = service.send_invitations(ProfileFactory(), ["ann@example.com"]).invitations[0]

        content = graphql_client(
            SIGNUP,
            variables={"input": {"token": invitation.invitation_token, "password": "x"}},
        ).json()

        assert error_code(content) == "signup_disabled"

    def test_signs_the_invitee_up_anonymously(self, graphql_client, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_SIGNUP_ENABLED = True
        invitation = service.send_invitations(ProfileFactory(), ["ann@example.com"]).invitations[0]

        content = graphql_client(
            SIGNUP,
            variables={
                "input": {
                    "token": invitation.invitation_token,
                    "password": "c0rrect-Horse-battery",
                    "firstName": "Ann",
                }
            },
        ).json()

        assert content["data"]["profileAcceptInvitationWithSignup"] == {
            "success": True,
            "email": "ann@example.com",
        }
        user = User.objects.get(email="ann@example.com")
        assert user.first_name == "Ann"
        invitation.refresh_from_db()
        assert (invitation.status, invitation.user) == (Status.ACTIVE, user)


class TestCancel:
    def test_with_history_returns_the_cancelled_row(
        self, django_user_client, graphql_user_client, settings
    ) -> None:
        settings.BASEAPP_PROFILES_INVITATION_KEEP_HISTORY = True
        profile = ProfileFactory(owner=django_user_client.user)
        invitation = service.send_invitations(profile, ["ann@example.com"]).invitations[0]

        content = graphql_user_client(
            CANCEL, variables={"input": {"invitationId": invitation.relay_id}}
        ).json()

        data = content["data"]["profileCancelInvitation"]
        assert data["success"] is True
        assert data["profileUserRole"]["status"] == "CANCELLED"
        assert data["profileUserRole"]["deactivatedAt"] is not None

    def test_without_history_deletes(self, django_user_client, graphql_user_client) -> None:
        profile = ProfileFactory(owner=django_user_client.user)
        invitation = service.send_invitations(profile, ["ann@example.com"]).invitations[0]

        content = graphql_user_client(
            CANCEL, variables={"input": {"invitationId": invitation.relay_id}}
        ).json()

        assert content["data"]["profileCancelInvitation"]["profileUserRole"] is None
        assert not ProfileUserRole.objects.filter(pk=invitation.pk).exists()


class TestMemberStatus:
    def test_an_admin_deactivates_and_reactivates_a_member(
        self, django_user_client, graphql_user_client
    ) -> None:
        profile = ProfileFactory(owner=None)
        ProfileUserRoleFactory(profile=profile, user=django_user_client.user, role=ADMIN)
        member = ProfileUserRoleFactory(profile=profile, role=MANAGER)
        variables = {"input": {"profileId": profile.relay_id, "userId": member.user.relay_id}}

        content = graphql_user_client(DEACTIVATE, variables=variables).json()
        assert content["data"]["profileMemberDeactivate"]["profileUserRole"]["status"] == "INACTIVE"
        member.refresh_from_db()
        assert member.deactivated_by == django_user_client.user

        content = graphql_user_client(REACTIVATE, variables=variables).json()
        assert content["data"]["profileMemberReactivate"]["profileUserRole"]["status"] == "ACTIVE"

    def test_a_manager_cannot(self, django_user_client, graphql_user_client) -> None:
        profile = ProfileFactory()
        ProfileUserRoleFactory(profile=profile, user=django_user_client.user, role=MANAGER)
        member = ProfileUserRoleFactory(profile=profile, role=MANAGER)

        content = graphql_user_client(
            DEACTIVATE,
            variables={"input": {"profileId": profile.relay_id, "userId": member.user.relay_id}},
        ).json()

        assert error_code(content) == "permission_required"

    def test_unknown_member(self, django_user_client, graphql_user_client) -> None:
        profile = ProfileFactory(owner=django_user_client.user)

        content = graphql_user_client(
            REACTIVATE,
            variables={"input": {"profileId": profile.relay_id, "userId": UserFactory().relay_id}},
        ).json()

        assert error_code(content) == "not_found"


class TestLastAdminThroughTheMutations:
    @pytest.fixture
    def sole_admin(self, django_user_client) -> "ProfileUserRole":
        return ProfileUserRoleFactory(
            profile=ProfileFactory(owner=None), user=django_user_client.user, role=ADMIN
        )

    def _variables(self, admin) -> dict:
        return {"profileId": admin.profile.relay_id, "userId": admin.user.relay_id}

    def test_demoting(self, sole_admin, graphql_user_client) -> None:
        content = graphql_user_client(
            UPDATE_ROLE, variables={"input": {**self._variables(sole_admin), "roleType": "MANAGER"}}
        ).json()
        assert error_code(content) == "last_admin"

    def test_removing(self, sole_admin, graphql_user_client) -> None:
        content = graphql_user_client(
            DELETE_ROLE, variables={"input": self._variables(sole_admin)}
        ).json()
        assert error_code(content) == "last_admin"
        assert ProfileUserRole.objects.filter(pk=sole_admin.pk).exists()

    def test_deactivating(self, sole_admin, graphql_user_client) -> None:
        content = graphql_user_client(
            DEACTIVATE, variables={"input": self._variables(sole_admin)}
        ).json()
        assert error_code(content) == "last_admin"


def test_with_history_a_declined_user_can_be_added_directly(
    django_user_client, graphql_user_client, settings
) -> None:
    settings.BASEAPP_PROFILES_INVITATION_KEEP_HISTORY = True
    profile = ProfileFactory(owner=django_user_client.user)
    user = UserFactory(email="ann@example.com")
    invitation = service.send_invitations(profile, ["ann@example.com"]).invitations[0]
    service.decline_invitation(invitation.invitation_token, user)

    content = graphql_user_client(
        """
        mutation Add($input: ProfileUserRoleCreateInput!) {
            profileUserRoleCreate(input: $input) { profileUserRoles { status } }
        }
        """,
        variables={"input": {"profileId": profile.relay_id, "usersIds": [user.relay_id]}},
    ).json()

    assert content["data"]["profileUserRoleCreate"]["profileUserRoles"] == [{"status": "ACTIVE"}]
    assert ProfileUserRole.objects.filter(profile=profile, user=user).count() == 2
