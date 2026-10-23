"""
`BASEAPP_PROFILES_INVITATION_CAN_INVITE_MEMBER`: an invitation that claims an existing ACTIVE
row, such as a member imported ahead of time whose account was never used.
"""

from datetime import timedelta

import pytest
import swapper
from django.contrib.auth import get_user_model
from django.utils import timezone

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles import signals, tasks
from baseapp_profiles.exceptions import ProfileMembershipError
from baseapp_profiles.services import invitations as service

from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

User = get_user_model()
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
ADMIN = ProfileUserRole.ProfileRoles.ADMIN
MANAGER = ProfileUserRole.ProfileRoles.MANAGER
Status = ProfileUserRole.ProfileRoleStatus
PASSWORD = "c0rrect-Horse-battery"  # NOSONAR


def is_placeholder(membership) -> bool:
    user = membership.user
    return user is not None and not user.is_active and not user.has_usable_password()


@pytest.fixture
def placeholder() -> "ProfileUserRole":
    user = UserFactory(email="ann@example.com", is_active=False)
    user.set_unusable_password()
    user.save()
    return ProfileUserRoleFactory(profile=ProfileFactory(owner=None), user=user, role=ADMIN)


@pytest.fixture
def claims(settings) -> None:
    settings.BASEAPP_PROFILES_INVITATION_CAN_INVITE_MEMBER = (
        "baseapp_profiles.tests.test_member_claims.is_placeholder"
    )
    settings.BASEAPP_PROFILES_INVITATION_SIGNUP_ENABLED = True


def claim(placeholder, **kwargs) -> "ProfileUserRole":
    return service.send_invitations(
        placeholder.profile, ["ann@example.com"], role=MANAGER, **kwargs
    ).invitations[0]


def test_inviting_a_member_is_refused_by_default(placeholder) -> None:
    with pytest.raises(ProfileMembershipError) as excinfo:
        claim(placeholder)

    assert excinfo.value.code == "already_member"


def test_a_member_the_hook_refuses_is_still_refused(claims) -> None:
    member = ProfileUserRoleFactory(user=UserFactory(email="bob@example.com"))

    with pytest.raises(ProfileMembershipError) as excinfo:
        service.send_invitations(member.profile, ["bob@example.com"])

    assert excinfo.value.code == "already_member"


class TestSend:
    def test_the_invitation_is_carried_on_the_member_row(
        self, claims, placeholder, mailoutbox
    ) -> None:
        inviter = UserFactory()

        invitation = claim(placeholder, invited_by=inviter, message="Your account is ready")

        assert invitation.pk == placeholder.pk
        assert ProfileUserRole.objects.count() == 1
        invitation.refresh_from_db()
        # Still a member with the same role; only the invitation fields were written.
        assert (invitation.status, invitation.role) == (Status.ACTIVE, ADMIN)
        assert invitation.invitation_token
        assert invitation.invited_email == "ann@example.com"
        assert invitation.invited_by == inviter
        assert invitation.message == "Your account is ready"
        assert invitation.sent_count == 1
        assert invitation.invitation_expires_at > timezone.now()
        assert mailoutbox[0].to == ["ann@example.com"]
        assert service.is_member_claim(invitation)

    def test_an_open_claim_is_not_sent_twice(self, claims, placeholder) -> None:
        claim(placeholder)

        with pytest.raises(ProfileMembershipError) as excinfo:
            claim(placeholder)

        assert excinfo.value.code == "duplicate_invitation"

    def test_an_expired_claim_is_reopened(self, claims, placeholder) -> None:
        first = claim(placeholder)
        old_token = first.invitation_token
        first.invitation_expires_at = timezone.now() - timedelta(days=1)
        first.save(update_fields=["invitation_expires_at"])

        second = claim(placeholder)

        assert second.pk == placeholder.pk
        assert second.invitation_token != old_token
        assert second.status == Status.ACTIVE

    def test_the_celery_task_sends_a_claim(self, claims, placeholder, mailoutbox) -> None:
        invitation = claim(placeholder)
        mailoutbox.clear()

        assert tasks.send_invitation_email_task(invitation.pk) is True
        assert len(mailoutbox) == 1


class TestManage:
    def test_resend_renews_the_token(self, claims, placeholder) -> None:
        invitation = claim(placeholder)
        old_token = invitation.invitation_token

        result = service.resend_invitation(invitation)

        assert result.invitations[0].pk == placeholder.pk
        invitation.refresh_from_db()
        assert invitation.invitation_token != old_token
        assert invitation.status == Status.ACTIVE
        assert invitation.sent_count == 2

    def test_resend_of_a_plain_member_is_refused(self, claims) -> None:
        member = ProfileUserRoleFactory()

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.resend_invitation(member)

        assert excinfo.value.code == "invalid_status"

    def test_a_stale_resend_does_not_reopen_an_accepted_claim(self, claims, placeholder) -> None:
        invitation = claim(placeholder)
        stale = ProfileUserRole.objects.get(pk=invitation.pk)
        service.accept_invitation_with_signup(invitation.invitation_token, password=PASSWORD)

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.resend_invitation(stale)

        assert excinfo.value.code == "invalid_status"
        invitation.refresh_from_db()
        assert invitation.responded_at is not None
        assert not service.is_member_claim(invitation)

    def test_cancel_clears_the_token_and_keeps_the_member(
        self, claims, placeholder, signal_recorder, django_capture_on_commit_callbacks
    ) -> None:
        cancelled = signal_recorder(signals.invitation_cancelled)
        invitation = claim(placeholder)
        token = invitation.invitation_token

        with django_capture_on_commit_callbacks(execute=True):
            service.cancel_invitation(invitation)

        invitation.refresh_from_db()
        assert invitation.invitation_token is None
        assert invitation.status == Status.ACTIVE
        assert service.lookup_invitation(token) is None
        assert len(cancelled) == 1

    def test_release_sends_a_held_claim(self, claims, placeholder, settings, mailoutbox) -> None:
        settings.BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK = lambda invitation: True
        held = service.send_invitations(placeholder.profile, ["ann@example.com"]).held[0]
        assert mailoutbox == []

        assert service.release_invitation(held) is True
        assert len(mailoutbox) == 1


class TestRespond:
    def test_lookup_reports_pending_then_expired(self, claims, placeholder) -> None:
        invitation = claim(placeholder)

        public = service.lookup_invitation(invitation.invitation_token)
        assert public.status == Status.PENDING
        assert public.requires_sign_in is False

        invitation.invitation_expires_at = timezone.now() - timedelta(minutes=1)
        invitation.save(update_fields=["invitation_expires_at"])
        assert service.lookup_invitation(invitation.invitation_token).status == Status.EXPIRED

    def test_signup_claims_the_account_on_the_same_row(
        self, claims, placeholder, signal_recorder, django_capture_on_commit_callbacks
    ) -> None:
        accepted = signal_recorder(signals.invitation_accepted)
        invitation = claim(placeholder)

        with django_capture_on_commit_callbacks(execute=True):
            result = service.accept_invitation_with_signup(
                invitation.invitation_token, password=PASSWORD, first_name="Ann"
            )

        assert result.pk == placeholder.pk
        result.refresh_from_db()
        assert (result.status, result.role) == (Status.ACTIVE, ADMIN)
        assert result.responded_at is not None
        user = User.objects.get(pk=placeholder.user_id)
        assert user.is_active and user.check_password(PASSWORD)
        assert user.first_name == "Ann"
        assert [(call["instance"].pk, call["created_user"]) for call in accepted] == [
            (placeholder.pk, False)
        ]
        # Answered: the link now reports the membership, and cannot be used again.
        assert not service.is_member_claim(result)
        assert service.lookup_invitation(invitation.invitation_token).status == Status.ACTIVE
        with pytest.raises(ProfileMembershipError) as excinfo:
            service.accept_invitation_with_signup(invitation.invitation_token, password=PASSWORD)
        assert excinfo.value.code in ("user_exists", "already_responded")

    def test_an_expired_claim_cannot_be_accepted(self, claims, placeholder) -> None:
        invitation = claim(placeholder)
        invitation.invitation_expires_at = timezone.now() - timedelta(minutes=1)
        invitation.save(update_fields=["invitation_expires_at"])

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.accept_invitation_with_signup(invitation.invitation_token, password=PASSWORD)

        assert excinfo.value.code == "expired_invitation"
        invitation.refresh_from_db()
        assert invitation.status == Status.ACTIVE

    def test_signed_in_accept_and_decline_keep_the_membership(self, settings) -> None:
        # A project whose claims go to existing, active accounts.
        settings.BASEAPP_PROFILES_INVITATION_CAN_INVITE_MEMBER = lambda membership: True
        member = ProfileUserRoleFactory(user=UserFactory(email="bob@example.com"))
        invitation = service.send_invitations(member.profile, ["bob@example.com"]).invitations[0]

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.accept_invitation(invitation.invitation_token, UserFactory())
        assert excinfo.value.code == "wrong_user"

        service.decline_invitation(invitation.invitation_token, member.user)
        member.refresh_from_db()
        assert member.status == Status.ACTIVE
        assert not service.is_member_claim(member)

        invitation = service.send_invitations(member.profile, ["bob@example.com"]).invitations[0]
        accepted = service.accept_invitation(invitation.invitation_token, member.user)
        assert (accepted.pk, accepted.status) == (member.pk, Status.ACTIVE)

    def test_graphql_lifecycle(self, claims, placeholder, graphql_client) -> None:
        invitation = claim(placeholder)

        preview = graphql_client(
            """
            query Preview($token: String!) {
                profileInvitationPreview(token: $token) { status requiresSignIn }
                profileInvitation(token: $token) { status isExpired profile { id } }
            }
            """,
            variables={"token": invitation.invitation_token},
        ).json()["data"]

        assert preview["profileInvitationPreview"] == {
            "status": "PENDING",
            "requiresSignIn": False,
        }
        assert preview["profileInvitation"] == {
            "status": "ACTIVE",
            "isExpired": False,
            "profile": {"id": placeholder.profile.relay_id},
        }

        content = graphql_client(
            """
            mutation Signup($input: ProfileAcceptInvitationWithSignupInput!) {
                profileAcceptInvitationWithSignup(input: $input) { success email }
            }
            """,
            variables={"input": {"token": invitation.invitation_token, "password": PASSWORD}},
        ).json()

        assert content["data"]["profileAcceptInvitationWithSignup"] == {
            "success": True,
            "email": "ann@example.com",
        }
