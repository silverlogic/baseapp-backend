"""
What the invitation services do with a row that changed after the caller read it, and with
the failures around sending: a stale copy, a superseded token, a broker or receiver that fails.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
import swapper
from django.contrib.auth import get_user_model
from django.utils import timezone

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles import signals, tasks
from baseapp_profiles.exceptions import ProfileMembershipError
from baseapp_profiles.services import invitations as service
from baseapp_profiles.services import members as member_service

from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

User = get_user_model()
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
MANAGER = ProfileUserRole.ProfileRoles.MANAGER
Status = ProfileUserRole.ProfileRoleStatus
PASSWORD = "c0rrect-Horse-battery"  # NOSONAR


def hold_everything(invitation) -> bool:
    return True


@pytest.fixture
def profile() -> "ProfileUserRole":
    return ProfileFactory(owner=UserFactory(), name="Acme")


def invite(profile, email="ann@example.com", **kwargs) -> "ProfileUserRole":
    return service.send_invitations(profile, [email], **kwargs).invitations[0]


def stale_copy(invitation) -> "ProfileUserRole":
    return ProfileUserRole.objects.select_related("profile").get(pk=invitation.pk)


class TestStaleCopies:
    def test_expiring_a_stale_copy_leaves_an_accepted_invitation_alone(
        self, profile, signal_recorder
    ) -> None:
        user = UserFactory(email="ann@example.com")
        invitation = invite(profile)
        stale = stale_copy(invitation)
        service.accept_invitation(invitation.invitation_token, user)
        expired = signal_recorder(signals.invitation_expired)

        assert service.expire_invitation(stale) is False

        invitation.refresh_from_db()
        assert invitation.status == Status.ACTIVE
        assert stale.status == Status.PENDING
        assert expired == []

    def test_expiring_a_stale_copy_leaves_a_renewed_invitation_alone(self, profile) -> None:
        invitation = invite(profile)
        stale = stale_copy(invitation)
        service.resend_invitation(invitation)

        assert service.expire_invitation(stale) is False

        invitation.refresh_from_db()
        assert invitation.status == Status.PENDING

    def test_the_sweep_counts_only_what_it_expired(self, profile) -> None:
        invitation = invite(profile)

        assert service.expire_invitations(now=timezone.now() + timedelta(days=365)) == 1

        invitation.refresh_from_db()
        assert invitation.status == Status.EXPIRED

    def test_a_token_replaced_by_a_resend_no_longer_answers(self, profile) -> None:
        user = UserFactory(email="ann@example.com")
        invitation = invite(profile)
        stale = stale_copy(invitation)
        service.resend_invitation(invitation)

        # What a response sees when the resend commits between its read and its lock.
        with patch.object(service, "get_invitation_by_token", return_value=stale):
            with pytest.raises(ProfileMembershipError) as error:
                service.accept_invitation(stale.invitation_token, user)

        assert error.value.code == "invalid_token"
        invitation.refresh_from_db()
        assert invitation.status == Status.PENDING

    def test_a_hold_does_not_clear_the_expiry_of_a_newer_token(self, profile, settings) -> None:
        invitation = invite(profile)
        stale = stale_copy(invitation)
        service.resend_invitation(invitation)
        settings.BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK = hold_everything

        result = service.SentInvitations()
        service._deliver_or_hold(stale, inviter=None, result=result)

        invitation.refresh_from_db()
        assert invitation.invitation_expires_at is not None


class TestRelease:
    @pytest.fixture
    def held(self, profile, settings) -> "ProfileUserRole":
        settings.BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK = hold_everything
        return invite(profile)

    def test_releasing_twice_sends_once(self, held, mailoutbox) -> None:
        again = stale_copy(held)
        assert service.release_invitation(held) is True

        with pytest.raises(ProfileMembershipError) as error:
            service.release_invitation(again)

        assert error.value.code == "invalid_status"
        assert len(mailoutbox) == 1

    def test_a_cancelled_invitation_is_not_released(self, held, settings, mailoutbox) -> None:
        settings.BASEAPP_PROFILES_INVITATION_KEEP_HISTORY = True
        stale = stale_copy(held)
        service.cancel_invitation(held)

        with pytest.raises(ProfileMembershipError):
            service.release_invitation(stale)

        assert mailoutbox == []

    def test_a_release_whose_email_fails_stays_held(self, held, mailoutbox) -> None:
        with patch("baseapp_profiles.emails.send_invitation_email", side_effect=OSError):
            assert service.release_invitation(held) is False

        held.refresh_from_db()
        assert held.invitation_expires_at is None
        assert service.release_invitation(held) is True
        assert len(mailoutbox) == 1


class TestPreSendHook:
    def test_a_hook_that_cannot_be_loaded_holds_the_invitation(
        self, profile, settings, mailoutbox
    ) -> None:
        settings.BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK = "no.such.module.hook"

        result = service.send_invitations(profile, ["ann@example.com", "bob@example.com"])

        assert len(result.held) == 2
        assert mailoutbox == []


class TestQueuedEmails:
    @pytest.fixture(autouse=True)
    def queued_sends(self, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_ASYNC_SEND = True
        settings.CELERY_TASK_ALWAYS_EAGER = False

    def test_a_broker_failure_does_not_stop_the_batch(
        self, profile, django_capture_on_commit_callbacks
    ) -> None:
        with patch.object(
            tasks.send_invitation_email_task, "delay", side_effect=[OSError("broker down"), None]
        ) as delay:
            with django_capture_on_commit_callbacks(execute=True):
                result = service.send_invitations(profile, ["ann@example.com", "bob@example.com"])

        assert delay.call_count == 2
        assert len(result.invitations) == 2

    def test_an_email_queued_for_a_replaced_token_is_dropped(self, profile, mailoutbox) -> None:
        invitation = invite(profile)
        old_token = invitation.invitation_token
        with patch.object(tasks.send_invitation_email_task, "delay"):
            service.resend_invitation(invitation)
        mailoutbox.clear()

        assert tasks.send_invitation_email_task(invitation.pk, None, old_token) is False
        assert mailoutbox == []

        invitation.refresh_from_db()
        assert (
            tasks.send_invitation_email_task(invitation.pk, None, invitation.invitation_token)
            is True
        )
        assert len(mailoutbox) == 1


class TestSignals:
    def test_a_failing_receiver_does_not_fail_the_change_or_the_other_receivers(
        self, profile, signal_recorder, django_capture_on_commit_callbacks
    ) -> None:
        def broken(sender, **kwargs) -> None:
            raise RuntimeError("notification service down")

        signals.member_added.connect(broken, weak=False)
        added = signal_recorder(signals.member_added)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                memberships = member_service.add_members(profile, [UserFactory(), UserFactory()])
        finally:
            signals.member_added.disconnect(broken)

        assert len(memberships) == 2
        assert len(added) == 2


class TestStaleAddresses:
    def test_inviting_an_address_a_deactivated_member_no_longer_uses(self, profile) -> None:
        member = UserFactory(email="old@example.com")
        membership = ProfileUserRoleFactory(
            profile=profile,
            user=member,
            role=MANAGER,
            status=Status.INACTIVE,
            invited_email="old@example.com",
        )
        member.email = "new@example.com"
        member.save()

        invitation = invite(profile, "old@example.com")

        # The membership stays the member's; the invitation is a row of its own, bound to
        # nobody until whoever holds the address answers.
        assert invitation.pk != membership.pk
        assert invitation.user is None
        membership.refresh_from_db()
        assert membership.user == member
        assert membership.status == Status.INACTIVE
        assert membership.invited_email is None

    def test_a_deactivated_member_is_still_invited_back_on_their_row(self, profile) -> None:
        member = UserFactory(email="ann@example.com")
        membership = ProfileUserRoleFactory(
            profile=profile,
            user=member,
            role=MANAGER,
            status=Status.INACTIVE,
            invited_email="ann@example.com",
        )

        invitation = invite(profile)

        assert invitation.pk == membership.pk
        assert invitation.user == member
        assert invitation.status == Status.PENDING

    def test_a_declined_row_found_by_a_stale_address_is_rebound(self, profile) -> None:
        former = UserFactory(email="old@example.com")
        declined = ProfileUserRoleFactory(
            profile=profile,
            user=former,
            role=MANAGER,
            status=Status.DECLINED,
            invited_email="old@example.com",
        )
        former.email = "new@example.com"
        former.save()

        invitation = invite(profile, "old@example.com")

        assert invitation.pk == declined.pk
        assert invitation.user is None


class TestSignup:
    def test_the_account_is_locked_and_read_again_before_it_is_activated(
        self, profile, settings
    ) -> None:
        settings.BASEAPP_PROFILES_INVITATION_SIGNUP_ENABLED = True
        account = UserFactory(email="ann@example.com", is_active=False, last_login=None)
        invitation = invite(profile)
        stale = stale_copy(invitation)
        assert stale.user == account  # loaded, as the first read of a signup does
        # Another invitation's signup activates the account in the meantime.
        User.objects.filter(pk=account.pk).update(is_active=True)

        with patch.object(service, "get_invitation_by_token", return_value=stale):
            with pytest.raises(ProfileMembershipError) as error:
                service.accept_invitation_with_signup(stale.invitation_token, password=PASSWORD)

        assert error.value.code == "user_exists"


class TestMembershipCheck:
    @pytest.mark.parametrize("status", [Status.PENDING, Status.INACTIVE, Status.DECLINED])
    def test_only_active_members_count_as_members(self, profile, status) -> None:
        row = ProfileUserRoleFactory(profile=profile, role=MANAGER, status=status)

        assert profile.check_if_member(row.user) is False

    def test_active_members_and_the_owner_are_members(self, profile) -> None:
        row = ProfileUserRoleFactory(profile=profile, role=MANAGER, status=Status.ACTIVE)

        assert profile.check_if_member(row.user) is True
        assert profile.check_if_member(profile.owner) is True
