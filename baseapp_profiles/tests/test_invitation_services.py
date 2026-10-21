from datetime import timedelta
from unittest.mock import patch

import pytest
import swapper
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles import signals, tasks
from baseapp_profiles.exceptions import ProfileMembershipError
from baseapp_profiles.services import invitations as service
from baseapp_profiles.services.invitations import Invitee

from .factories import ProfileFactory, ProfileUserRoleFactory

pytestmark = pytest.mark.django_db

User = get_user_model()
Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
ADMIN = ProfileUserRole.ProfileRoles.ADMIN
MANAGER = ProfileUserRole.ProfileRoles.MANAGER
Status = ProfileUserRole.ProfileRoleStatus
PASSWORD = "c0rrect-Horse-battery"  # NOSONAR

HOOK_CALLS = []


def hold_everything(invitation) -> bool:
    HOOK_CALLS.append(invitation.pk)
    return True


def hold_nothing(invitation) -> bool:
    return False


def broken_hook(invitation) -> bool:
    raise RuntimeError("review service down")


def reactivate_anyone(user, invitation) -> bool:
    return True


@pytest.fixture
def owner() -> "User":
    return UserFactory(first_name="Olive", last_name="Owner")


@pytest.fixture
def profile(owner) -> "Profile":
    return ProfileFactory(owner=owner, name="Acme")


@pytest.fixture
def keep_history(settings) -> None:
    settings.BASEAPP_PROFILES_INVITATION_KEEP_HISTORY = True


@pytest.fixture
def signup_enabled(settings) -> None:
    settings.BASEAPP_PROFILES_INVITATION_SIGNUP_ENABLED = True


def invite(profile, email="ann@example.com", **kwargs) -> "ProfileUserRole":
    return service.send_invitations(profile, [email], **kwargs).invitations[0]


def make_overdue(invitation) -> None:
    invitation.invitation_expires_at = timezone.now() - timedelta(days=1)
    invitation.save(update_fields=["invitation_expires_at"])


class TestSendInvitations:
    def test_records_the_invitee_the_note_and_the_sender(self, profile, owner, mailoutbox) -> None:
        result = service.send_invitations(
            profile,
            [Invitee("Ann@Example.com ", "Ann", "Lee")],
            role=ADMIN,
            invited_by=owner,
            message="Welcome aboard",
        )

        invitation = result.invitations[0]
        assert result.emails_sent == 1
        assert invitation.status == Status.PENDING
        assert invitation.invited_email == "ann@example.com"
        assert (invitation.invited_first_name, invitation.invited_last_name) == ("Ann", "Lee")
        assert invitation.message == "Welcome aboard"
        assert invitation.invited_by == owner
        assert invitation.role == ADMIN
        invitation.refresh_from_db()
        assert invitation.sent_count == 1
        assert invitation.last_sent_at is not None

        assert len(mailoutbox) == 1
        email = mailoutbox[0]
        assert email.to == ["ann@example.com"]
        assert "Welcome aboard" in email.body
        assert "Hi Ann Lee" in email.body
        assert "Olive Owner" in email.body
        assert invitation.invitation_token in email.body

    def test_takes_strings_and_dicts_and_drops_duplicates(self, profile) -> None:
        result = service.send_invitations(
            profile,
            ["a@example.com", {"email": "B@example.com", "first_name": "Bea"}, "A@example.com"],
        )

        assert [i.invited_email for i in result.invitations] == ["a@example.com", "b@example.com"]
        assert result.invitations[1].invited_first_name == "Bea"
        assert all(i.role == MANAGER for i in result.invitations)

    def test_refuses_an_empty_list_and_an_unassignable_role(self, profile) -> None:
        with pytest.raises(ProfileMembershipError) as excinfo:
            service.send_invitations(profile, ["  "])
        assert excinfo.value.code == "invalid_input"

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.send_invitations(profile, ["a@example.com"], role=42)
        assert excinfo.value.code == "invalid_input"

    def test_a_conflict_rolls_back_the_whole_batch(self, profile) -> None:
        ProfileUserRoleFactory(profile=profile, user=UserFactory(email="member@example.com"))

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.send_invitations(profile, ["new@example.com", "member@example.com"])

        assert excinfo.value.code == "already_member"
        assert not ProfileUserRole.objects.filter(invited_email="new@example.com").exists()

    def test_a_pending_invitation_blocks_a_second_one(self, profile) -> None:
        invite(profile)

        with pytest.raises(ProfileMembershipError) as excinfo:
            invite(profile)
        assert excinfo.value.code == "duplicate_invitation"

    def test_a_failed_email_keeps_the_invitation_but_is_not_counted(self, profile) -> None:
        with patch(
            "baseapp_profiles.emails.send_invitation_email", side_effect=Exception("SMTP down")
        ):
            result = service.send_invitations(profile, ["ann@example.com"])

        invitation = result.invitations[0]
        invitation.refresh_from_db()
        assert result.emails_sent == 0
        assert invitation.status == Status.PENDING
        assert invitation.sent_count == 0

    def test_invitation_sent_fires_after_commit(
        self, profile, owner, signal_recorder, django_capture_on_commit_callbacks
    ) -> None:
        calls = signal_recorder(signals.invitation_sent)

        with django_capture_on_commit_callbacks(execute=True):
            invitation = invite(profile, invited_by=owner)

        assert len(calls) == 1
        assert calls[0]["sender"] is ProfileUserRole
        assert calls[0]["instance"].pk == invitation.pk
        assert calls[0]["inviter"] == owner


class TestInvitationHistory:
    def test_without_history_a_reinvite_reuses_the_declined_row(self, profile) -> None:
        invitation = invite(profile)
        invitation.status = Status.DECLINED
        invitation.save()

        again = invite(profile)

        assert again.pk == invitation.pk
        assert ProfileUserRole.objects.filter(profile=profile).count() == 1

    @pytest.mark.usefixtures("keep_history")
    def test_a_reinvite_after_decline_keeps_the_old_row(self, profile) -> None:
        user = UserFactory(email="ann@example.com")
        declined = invite(profile)
        service.decline_invitation(declined.invitation_token, user)

        again = invite(profile, message="Second try")

        declined.refresh_from_db()
        assert again.pk != declined.pk
        assert declined.status == Status.DECLINED
        assert again.status == Status.PENDING
        assert again.user == user
        assert again.message == "Second try"

    @pytest.mark.usefixtures("keep_history")
    def test_a_reinvite_after_expiry_keeps_the_expired_row(
        self, profile, signal_recorder, django_capture_on_commit_callbacks
    ) -> None:
        calls = signal_recorder(signals.invitation_expired)
        first = invite(profile)
        make_overdue(first)

        with django_capture_on_commit_callbacks(execute=True):
            again = invite(profile)

        first.refresh_from_db()
        assert first.status == Status.EXPIRED
        assert again.pk != first.pk
        assert [c["instance"].pk for c in calls] == [first.pk]

    @pytest.mark.usefixtures("keep_history")
    def test_a_reinvite_brings_a_deactivated_member_back_on_the_same_row(self, profile) -> None:
        user = UserFactory(email="ann@example.com")
        member = ProfileUserRoleFactory(profile=profile, user=user, status=Status.INACTIVE)

        again = invite(profile)

        assert again.pk == member.pk
        assert again.status == Status.PENDING
        assert again.invited_email == "ann@example.com"

    @pytest.mark.usefixtures("keep_history")
    def test_closed_rows_may_repeat_but_open_rows_may_not(self, profile) -> None:
        for _ in range(2):
            ProfileUserRole.objects.create(
                profile=profile, invited_email="x@example.com", status=Status.DECLINED
            )
        ProfileUserRole.objects.create(
            profile=profile, invited_email="x@example.com", status=Status.PENDING
        )

        with pytest.raises(IntegrityError):
            ProfileUserRole.objects.create(
                profile=profile, invited_email="x@example.com", status=Status.PENDING
            )

    @pytest.mark.usefixtures("keep_history")
    def test_resending_an_expired_invitation_opens_a_new_row(self, profile, owner) -> None:
        first = invite(profile, message="Hello", role=ADMIN)
        service.expire_invitation(first)

        result = service.resend_invitation(first, by=owner)

        again = result.invitations[0]
        first.refresh_from_db()
        assert first.status == Status.EXPIRED
        assert again.pk != first.pk
        assert (again.role, again.message, again.invited_by) == (ADMIN, "Hello", owner)
        assert result.emails_sent == 1

    def test_without_history_resend_reuses_the_row_with_a_new_token(self, profile) -> None:
        first = invite(profile)
        old_token = first.invitation_token
        service.expire_invitation(first)

        result = service.resend_invitation(first)

        assert result.invitations[0].pk == first.pk
        assert result.invitations[0].status == Status.PENDING
        assert result.invitations[0].invitation_token != old_token

    def test_only_pending_or_expired_invitations_can_be_resent(self, profile) -> None:
        invitation = invite(profile)
        invitation.status = Status.DECLINED
        invitation.save()

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.resend_invitation(invitation)
        assert excinfo.value.code == "invalid_status"


class TestCancel:
    def test_without_history_cancel_deletes(
        self, profile, owner, signal_recorder, django_capture_on_commit_callbacks
    ) -> None:
        calls = signal_recorder(signals.invitation_cancelled)
        invitation = invite(profile)
        pk = invitation.pk

        with django_capture_on_commit_callbacks(execute=True):
            service.cancel_invitation(invitation, by=owner)

        assert not ProfileUserRole.objects.filter(pk=pk).exists()
        assert calls[0]["by"] == owner

    @pytest.mark.usefixtures("keep_history")
    def test_with_history_cancel_marks_the_row(self, profile, owner) -> None:
        invitation = invite(profile)

        service.cancel_invitation(invitation, by=owner)

        invitation.refresh_from_db()
        assert invitation.status == Status.CANCELLED
        assert invitation.deactivated_by == owner
        assert invitation.deactivated_at is not None
        assert service.lookup_invitation(invitation.invitation_token).status == Status.CANCELLED
        with pytest.raises(ProfileMembershipError) as excinfo:
            service.accept_invitation(invitation.invitation_token, UserFactory())
        assert excinfo.value.code == "cancelled_invitation"

    def test_only_pending_invitations_can_be_cancelled(self, profile) -> None:
        invitation = invite(profile)
        invitation.status = Status.ACTIVE
        invitation.save()

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.cancel_invitation(invitation)
        assert excinfo.value.code == "invalid_status"


class TestPreSendHook:
    def test_a_held_invitation_is_not_sent_and_does_not_expire(
        self, profile, settings, mailoutbox
    ) -> None:
        settings.BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK = (
            "baseapp_profiles.tests.test_invitation_services.hold_everything"
        )
        HOOK_CALLS.clear()

        result = service.send_invitations(profile, ["ann@example.com"])

        invitation = result.invitations[0]
        assert result.held == [invitation]
        assert result.emails_sent == 0
        assert HOOK_CALLS == [invitation.pk]
        assert mailoutbox == []
        invitation.refresh_from_db()
        assert invitation.invitation_expires_at is None
        assert invitation.sent_count == 0

        service.expire_invitations(now=timezone.now() + timedelta(days=365))
        invitation.refresh_from_db()
        assert invitation.status == Status.PENDING

    def test_release_sends_the_held_invitation(self, profile, owner, settings, mailoutbox) -> None:
        settings.BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK = hold_everything
        invitation = invite(profile, invited_by=owner)

        assert service.release_invitation(invitation) is True

        invitation.refresh_from_db()
        assert invitation.invitation_expires_at is not None
        assert invitation.sent_count == 1
        assert len(mailoutbox) == 1

    def test_only_pending_invitations_can_be_released(self, profile) -> None:
        invitation = invite(profile)
        invitation.status = Status.DECLINED
        invitation.save()

        with pytest.raises(ProfileMembershipError):
            service.release_invitation(invitation)

    def test_a_hook_that_fails_holds_the_invitation(self, profile, settings, mailoutbox) -> None:
        settings.BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK = broken_hook

        result = service.send_invitations(profile, ["ann@example.com"])

        assert len(result.held) == 1
        assert mailoutbox == []

    def test_a_hook_that_lets_it_through_sends(self, profile, settings, mailoutbox) -> None:
        settings.BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK = hold_nothing

        result = service.send_invitations(profile, ["ann@example.com"])

        assert result.emails_sent == 1
        assert len(mailoutbox) == 1

    def test_resend_asks_the_hook_again(self, profile, settings, mailoutbox) -> None:
        invitation = invite(profile)
        settings.BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK = hold_everything

        result = service.resend_invitation(invitation)

        assert result.held == [invitation]
        assert len(mailoutbox) == 1  # only the first send


class TestAsyncSend:
    def test_queues_a_task_on_commit_when_celery_runs_workers(
        self, profile, owner, settings, mailoutbox, django_capture_on_commit_callbacks
    ) -> None:
        settings.BASEAPP_PROFILES_INVITATION_ASYNC_SEND = True
        settings.CELERY_TASK_ALWAYS_EAGER = False

        with patch.object(tasks.send_invitation_email_task, "delay") as delay:
            with django_capture_on_commit_callbacks(execute=False) as callbacks:
                invitation = invite(profile, invited_by=owner)
            delay.assert_not_called()
            for callback in callbacks:
                callback()

        delay.assert_called_once_with(invitation.pk, owner.pk)
        assert mailoutbox == []

    def test_sends_inline_while_celery_is_eager(self, profile, settings, mailoutbox) -> None:
        settings.BASEAPP_PROFILES_INVITATION_ASYNC_SEND = True
        settings.CELERY_TASK_ALWAYS_EAGER = True

        result = service.send_invitations(profile, ["ann@example.com"])

        assert result.emails_sent == 1
        assert len(mailoutbox) == 1

    def test_the_task_sends_and_counts(self, profile, owner, mailoutbox) -> None:
        with patch("baseapp_profiles.emails.send_invitation_email"):
            invitation = invite(profile)

        assert tasks.send_invitation_email_task(invitation.pk, owner.pk) is True

        invitation.refresh_from_db()
        assert invitation.sent_count == 2
        assert "Olive Owner" in mailoutbox[0].body

    def test_the_task_skips_an_invitation_no_longer_pending(self, profile, mailoutbox) -> None:
        invitation = invite(profile)
        pk = invitation.pk
        mailoutbox.clear()
        service.cancel_invitation(invitation)

        assert tasks.send_invitation_email_task(pk) is False
        assert mailoutbox == []


class TestExpirySweep:
    def test_marks_overdue_invitations_expired(
        self, profile, signal_recorder, django_capture_on_commit_callbacks
    ) -> None:
        calls = signal_recorder(signals.invitation_expired)
        overdue = invite(profile, "old@example.com")
        make_overdue(overdue)
        current = invite(profile, "new@example.com")
        accepted = invite(profile, "done@example.com")
        accepted.status = Status.ACTIVE
        accepted.save()
        make_overdue(accepted)

        with django_capture_on_commit_callbacks(execute=True):
            assert tasks.expire_invitations() == 1

        for row in (overdue, current, accepted):
            row.refresh_from_db()
        assert overdue.status == Status.EXPIRED
        assert current.status == Status.PENDING
        assert accepted.status == Status.ACTIVE
        assert [c["instance"].pk for c in calls] == [overdue.pk]


class TestRespond:
    def test_accept_fires_invitation_accepted(
        self, profile, signal_recorder, django_capture_on_commit_callbacks
    ) -> None:
        calls = signal_recorder(signals.invitation_accepted)
        user = UserFactory(email="ann@example.com")
        invitation = invite(profile)

        with django_capture_on_commit_callbacks(execute=True):
            service.accept_invitation(invitation.invitation_token, user)

        invitation.refresh_from_db()
        assert invitation.status == Status.ACTIVE
        assert invitation.user == user
        assert calls[0]["user"] == user
        assert calls[0]["created_user"] is False

    def test_decline_fires_invitation_declined(
        self, profile, signal_recorder, django_capture_on_commit_callbacks
    ) -> None:
        calls = signal_recorder(signals.invitation_declined)
        user = UserFactory(email="ann@example.com")
        invitation = invite(profile)

        with django_capture_on_commit_callbacks(execute=True):
            service.decline_invitation(invitation.invitation_token, user)

        assert calls[0]["instance"].status == Status.DECLINED

    def test_an_expired_invitation_is_marked_and_refused(self, profile) -> None:
        invitation = invite(profile)
        make_overdue(invitation)

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.accept_invitation(invitation.invitation_token, UserFactory())

        assert excinfo.value.code == "expired_invitation"
        invitation.refresh_from_db()
        assert invitation.status == Status.EXPIRED

    def test_accepting_twice_is_refused(self, profile) -> None:
        user = UserFactory(email="ann@example.com")
        invitation = invite(profile)
        service.accept_invitation(invitation.invitation_token, user)

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.accept_invitation(invitation.invitation_token, user)
        assert excinfo.value.code == "already_responded"

    def test_a_member_cannot_accept_into_a_second_open_row(self, profile) -> None:
        user = UserFactory(email="ann@example.com")
        ProfileUserRoleFactory(profile=profile, user=user, status=Status.INACTIVE)
        invitation = ProfileUserRole.objects.create(
            profile=profile,
            invited_email="ann@example.com",
            status=Status.PENDING,
            invitation_token="t" * 64,
        )

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.accept_invitation(invitation.invitation_token, user)
        assert excinfo.value.code == "already_member"

    def test_an_unknown_token_is_refused(self) -> None:
        with pytest.raises(ProfileMembershipError) as excinfo:
            service.accept_invitation("nope", UserFactory())
        assert excinfo.value.code == "invalid_token"


class TestAcceptWithSignup:
    def test_is_disabled_unless_the_project_opts_in(self, profile) -> None:
        invitation = invite(profile)

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.accept_invitation_with_signup(invitation.invitation_token, password=PASSWORD)
        assert excinfo.value.code == "signup_disabled"

    @pytest.mark.usefixtures("signup_enabled")
    def test_creates_the_account_and_accepts(
        self, profile, signal_recorder, django_capture_on_commit_callbacks
    ) -> None:
        calls = signal_recorder(signals.invitation_accepted)
        invitation = invite(profile, "New.Person@example.com")

        with django_capture_on_commit_callbacks(execute=True):
            service.accept_invitation_with_signup(
                invitation.invitation_token, password=PASSWORD, first_name="New", last_name="P"
            )

        user = User.objects.get(email="new.person@example.com")
        assert user.check_password(PASSWORD)
        assert user.is_active
        assert user.is_email_verified
        assert (user.first_name, user.last_name) == ("New", "P")
        invitation.refresh_from_db()
        assert (invitation.status, invitation.user) == (Status.ACTIVE, user)
        assert calls[0]["created_user"] is True
        assert calls[0]["user"] == user

    @pytest.mark.usefixtures("signup_enabled")
    def test_activates_an_inactive_account(self, profile) -> None:
        dormant = UserFactory(email="ann@example.com", is_active=False)
        invitation = invite(profile)

        service.accept_invitation_with_signup(invitation.invitation_token, password=PASSWORD)

        dormant.refresh_from_db()
        assert dormant.is_active
        assert dormant.check_password(PASSWORD)
        assert User.objects.filter(email__iexact="ann@example.com").count() == 1

    @pytest.mark.usefixtures("signup_enabled")
    def test_an_active_account_must_sign_in(self, profile) -> None:
        active = UserFactory(email="ann@example.com")
        invitation = invite(profile)

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.accept_invitation_with_signup(invitation.invitation_token, password=PASSWORD)

        assert excinfo.value.code == "user_exists"
        active.refresh_from_db()
        assert not active.check_password(PASSWORD)
        invitation.refresh_from_db()
        assert invitation.status == Status.PENDING

    @pytest.mark.usefixtures("signup_enabled")
    def test_a_weak_password_creates_nothing(self, profile) -> None:
        invitation = invite(profile)

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.accept_invitation_with_signup(invitation.invitation_token, password="123")

        assert excinfo.value.code == "invalid_password"
        assert not User.objects.filter(email="ann@example.com").exists()
        invitation.refresh_from_db()
        assert invitation.status == Status.PENDING

    @pytest.mark.usefixtures("signup_enabled")
    def test_an_expired_invitation_is_refused(self, profile) -> None:
        invitation = invite(profile)
        make_overdue(invitation)

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.accept_invitation_with_signup(invitation.invitation_token, password=PASSWORD)
        assert excinfo.value.code == "expired_invitation"


class TestSignupReactivation:
    """Holding the token proves control of the inbox, not the right to undo a ban."""

    @pytest.mark.usefixtures("signup_enabled")
    @pytest.mark.parametrize("flags", [{"is_superuser": True}, {"is_staff": True}])
    def test_never_reactivates_staff_or_superusers(self, profile, settings, flags) -> None:
        settings.BASEAPP_PROFILES_INVITATION_SIGNUP_CAN_REACTIVATE = reactivate_anyone
        disabled = UserFactory(email="ann@example.com", is_active=False, **flags)
        invitation = invite(profile)

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.accept_invitation_with_signup(invitation.invitation_token, password=PASSWORD)

        assert excinfo.value.code == "account_inactive"
        disabled.refresh_from_db()
        assert not disabled.is_active
        assert not disabled.check_password(PASSWORD)
        invitation.refresh_from_db()
        assert invitation.status == Status.PENDING

    @pytest.mark.usefixtures("signup_enabled")
    def test_does_not_reactivate_an_account_that_has_been_used(self, profile) -> None:
        deactivated = UserFactory(
            email="ann@example.com", is_active=False, last_login=timezone.now()
        )
        invitation = invite(profile)

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.accept_invitation_with_signup(invitation.invitation_token, password=PASSWORD)

        assert excinfo.value.code == "account_inactive"
        deactivated.refresh_from_db()
        assert not deactivated.is_active

    @pytest.mark.usefixtures("signup_enabled")
    def test_a_project_can_decide_which_accounts_come_back(self, profile, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_SIGNUP_CAN_REACTIVATE = (
            "baseapp_profiles.tests.test_invitation_services.reactivate_anyone"
        )
        used = UserFactory(email="ann@example.com", is_active=False, last_login=timezone.now())
        invitation = invite(profile)

        service.accept_invitation_with_signup(invitation.invitation_token, password=PASSWORD)

        used.refresh_from_db()
        assert used.is_active
        invitation.refresh_from_db()
        assert (invitation.status, invitation.user) == (Status.ACTIVE, used)


class TestConcurrentResponses:
    """A cancel that lands between loading an invitation and answering it must win."""

    @pytest.fixture
    def cancel_midway(self, monkeypatch):
        """Cancel the invitation (through its own copy) right after the first identity check."""
        bind_user = service._bind_user
        state = {"done": False}

        def bind_then_cancel(invitation, user) -> None:
            bind_user(invitation, user)
            if not state["done"]:
                state["done"] = True
                service.cancel_invitation(ProfileUserRole.objects.get(pk=invitation.pk))

        monkeypatch.setattr(service, "_bind_user", bind_then_cancel)

    @pytest.mark.usefixtures("cancel_midway")
    @pytest.mark.parametrize("respond", [service.accept_invitation, service.decline_invitation])
    def test_a_deleted_invitation_is_not_recreated(self, profile, respond) -> None:
        invitee = UserFactory(email="ann@example.com")
        invitation = invite(profile)

        with pytest.raises(ProfileMembershipError) as excinfo:
            respond(invitation.invitation_token, invitee)

        assert excinfo.value.code == "invalid_token"
        assert not ProfileUserRole.objects.filter(profile=profile).exists()

    @pytest.mark.usefixtures("cancel_midway", "keep_history")
    @pytest.mark.parametrize("respond", [service.accept_invitation, service.decline_invitation])
    def test_a_cancelled_invitation_stays_cancelled(self, profile, respond) -> None:
        invitee = UserFactory(email="ann@example.com")
        invitation = invite(profile)

        with pytest.raises(ProfileMembershipError) as excinfo:
            respond(invitation.invitation_token, invitee)

        assert excinfo.value.code == "cancelled_invitation"
        invitation.refresh_from_db()
        assert invitation.status == Status.CANCELLED

    @pytest.mark.parametrize("history", [False, True])
    def test_cancel_leaves_an_accepted_invitation_alone(self, profile, settings, history) -> None:
        settings.BASEAPP_PROFILES_INVITATION_KEEP_HISTORY = history
        invitee = UserFactory(email="ann@example.com")
        stale = invite(profile)
        service.accept_invitation(stale.invitation_token, invitee)

        with pytest.raises(ProfileMembershipError) as excinfo:
            service.cancel_invitation(stale)

        assert excinfo.value.code == "invalid_status"
        assert ProfileUserRole.objects.get(pk=stale.pk).status == Status.ACTIVE


class TestLookup:
    def test_reports_only_the_public_summary(self, profile) -> None:
        invitation = invite(profile, role=ADMIN)

        public = service.lookup_invitation(invitation.invitation_token)

        assert public == service.PublicInvitation(
            profile_name="Acme",
            invited_email="ann@example.com",
            role=ADMIN,
            status=Status.PENDING,
            expires_at=invitation.invitation_expires_at,
        )

    def test_an_overdue_invitation_reads_expired_without_being_written(self, profile) -> None:
        invitation = invite(profile)
        make_overdue(invitation)

        assert service.lookup_invitation(invitation.invitation_token).status == Status.EXPIRED
        invitation.refresh_from_db()
        assert invitation.status == Status.PENDING

    def test_an_unknown_token_gives_nothing(self) -> None:
        assert service.lookup_invitation("missing") is None
        assert service.lookup_invitation("") is None
