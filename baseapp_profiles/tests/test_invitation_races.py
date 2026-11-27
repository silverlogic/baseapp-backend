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
ADMIN = ProfileUserRole.ProfileRoles.ADMIN
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


class TestLastAdminWithDeactivatedAccounts:
    def test_an_admin_whose_account_is_deactivated_does_not_count(self) -> None:
        profile = ProfileFactory(owner=None)
        admin = ProfileUserRoleFactory(profile=profile, role=ADMIN)
        leaving = ProfileUserRoleFactory(profile=profile, role=ADMIN)
        leaving.user.is_active = False
        leaving.user.save()

        for change in (
            lambda: member_service.remove_member(admin),
            lambda: member_service.deactivate_member(admin),
            lambda: member_service.change_member_role(admin, MANAGER),
        ):
            with pytest.raises(ProfileMembershipError) as error:
                change()
            assert error.value.code == "last_admin"

    def test_a_membership_removed_meanwhile_is_reported_as_not_found(self) -> None:
        membership = ProfileUserRoleFactory(profile=ProfileFactory(owner=None), role=MANAGER)
        stale = stale_copy(membership)
        member_service.remove_member(membership)

        with pytest.raises(ProfileMembershipError) as error:
            member_service.remove_member(stale)

        assert error.value.code == "not_found"


class TestSecondRound:
    def test_a_history_resend_binds_whoever_holds_the_address_now(self, profile, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_KEEP_HISTORY = True
        account = UserFactory(email="old@example.com")
        invitation = invite(profile, "old@example.com")
        assert invitation.user == account
        account.email = "new@example.com"
        account.save()
        invitation.invitation_expires_at = timezone.now() - timedelta(days=1)
        invitation.save(update_fields=["invitation_expires_at"])

        resent = service.resend_invitation(invitation).invitations[0]

        assert resent.pk != invitation.pk
        assert resent.invited_email == "old@example.com"
        assert resent.user is None

    def test_a_hold_is_not_written_to_a_cancelled_invitation(self, profile, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_KEEP_HISTORY = True
        invitation = invite(profile)
        stale = stale_copy(invitation)
        service.cancel_invitation(invitation)
        expires_at = ProfileUserRole.objects.get(pk=invitation.pk).invitation_expires_at
        settings.BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK = hold_everything

        result = service.SentInvitations()
        service._deliver_or_hold(stale, inviter=None, result=result)

        assert result.held == []
        assert ProfileUserRole.objects.get(pk=invitation.pk).invitation_expires_at == expires_at

    def test_signup_refuses_an_account_whose_email_changed_before_the_lock(
        self, profile, settings
    ) -> None:
        settings.BASEAPP_PROFILES_INVITATION_SIGNUP_ENABLED = True
        account = UserFactory(email="ann@example.com", is_active=False, last_login=None)
        invitation = invite(profile)
        stale = stale_copy(invitation)
        assert stale.user == account
        User.objects.filter(pk=account.pk).update(email="other@example.com")

        with patch.object(service, "get_invitation_by_token", return_value=stale):
            with pytest.raises(ProfileMembershipError) as error:
                service.accept_invitation_with_signup(stale.invitation_token, password=PASSWORD)

        assert error.value.code == "wrong_user"
        account.refresh_from_db()
        assert account.is_active is False

    def test_signup_refuses_a_name_the_user_model_cannot_hold(self, profile, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_SIGNUP_ENABLED = True
        invitation = invite(profile)
        limit = User._meta.get_field("first_name").max_length

        with pytest.raises(ProfileMembershipError) as error:
            service.accept_invitation_with_signup(
                invitation.invitation_token, password=PASSWORD, first_name="a" * (limit + 1)
            )

        assert error.value.code == "invalid_input"
        assert not User.objects.filter(email="ann@example.com").exists()

    def test_the_text_email_shows_names_and_the_note_as_typed(self, profile, mailoutbox) -> None:
        service.send_invitations(
            profile,
            [{"email": "ann@example.com", "first_name": "A & B"}],
            message="R&D <team>",
        )

        email = mailoutbox[0]
        assert "Hi A & B," in email.body
        assert "R&D <team>" in email.body
        html = email.alternatives[0][0]
        assert "A &amp; B" in html
        assert "R&amp;D &lt;team&gt;" in html

    def test_a_queued_email_is_not_sent_after_the_invitation_expired(
        self, profile, mailoutbox
    ) -> None:
        invitation = invite(profile)
        mailoutbox.clear()
        invitation.invitation_expires_at = timezone.now() - timedelta(minutes=1)
        invitation.save(update_fields=["invitation_expires_at"])

        assert tasks.send_invitation_email_task(invitation.pk) is False
        assert mailoutbox == []


class TestReleaseOfQueuedEmails:
    @pytest.fixture
    def held(self, profile, settings) -> "ProfileUserRole":
        settings.BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK = hold_everything
        invitation = invite(profile)
        settings.BASEAPP_PROFILES_INVITATION_ASYNC_SEND = True
        settings.CELERY_TASK_ALWAYS_EAGER = False
        return invitation

    def test_a_publish_that_fails_on_commit_puts_the_invitation_back_on_hold(
        self, held, django_capture_on_commit_callbacks
    ) -> None:
        with patch.object(tasks.send_invitation_email_task, "delay", side_effect=OSError):
            with django_capture_on_commit_callbacks(execute=True):
                assert service.release_invitation(held) is True

        held.refresh_from_db()
        assert held.invitation_expires_at is None

    def test_a_worker_that_cannot_send_puts_the_invitation_back_on_hold(
        self, held, django_capture_on_commit_callbacks
    ) -> None:
        with patch.object(tasks.send_invitation_email_task, "delay") as delay:
            with django_capture_on_commit_callbacks(execute=True):
                service.release_invitation(held)
        args = delay.call_args.args

        with patch("baseapp_profiles.emails.send_invitation_email", side_effect=OSError):
            assert tasks.send_invitation_email_task(*args) is False

        held.refresh_from_db()
        assert held.invitation_expires_at is None

    def test_a_failure_of_a_superseded_attempt_leaves_a_resend_alone(
        self, held, settings, django_capture_on_commit_callbacks
    ) -> None:
        with patch.object(tasks.send_invitation_email_task, "delay") as delay:
            with django_capture_on_commit_callbacks(execute=True):
                service.release_invitation(held)
            args = delay.call_args.args
            settings.BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK = None
            with django_capture_on_commit_callbacks(execute=True):
                service.resend_invitation(held)
        current = ProfileUserRole.objects.get(pk=held.pk)

        with patch("baseapp_profiles.emails.send_invitation_email", side_effect=OSError):
            assert tasks.send_invitation_email_task(*args) is False

        assert ProfileUserRole.objects.get(pk=held.pk).invitation_expires_at == (
            current.invitation_expires_at
        )


class TestThirdRound:
    def test_declining_a_claim_on_a_row_without_an_account_does_not_bind_the_decliner(
        self, profile, settings
    ) -> None:
        settings.BASEAPP_PROFILES_INVITATION_CAN_INVITE_MEMBER = lambda membership: True
        placeholder = ProfileUserRoleFactory(
            profile=profile,
            user=None,
            role=MANAGER,
            status=Status.ACTIVE,
            invited_email="bob@example.com",
        )
        claim = invite(profile, "bob@example.com")
        assert claim.pk == placeholder.pk
        decliner = UserFactory(email="bob@example.com")

        service.decline_invitation(claim.invitation_token, decliner)

        placeholder.refresh_from_db()
        assert placeholder.status == Status.ACTIVE
        assert placeholder.user is None
        assert not profile.check_if_member(decliner)

    def test_extra_fields_cannot_change_a_field_the_services_guard(self) -> None:
        admin = ProfileUserRoleFactory(profile=ProfileFactory(owner=None), role=ADMIN)

        for name in ("role", "status", "user", "user_id", "profile"):
            with pytest.raises(ValueError):
                member_service.update_member(admin, extra_fields={name: MANAGER})

        admin.refresh_from_db()
        assert admin.role == ADMIN

    def test_an_invitee_name_the_column_cannot_hold_is_refused(self, profile) -> None:
        limit = ProfileUserRole._meta.get_field("invited_first_name").max_length

        with pytest.raises(ProfileMembershipError) as error:
            service.send_invitations(
                profile, [{"email": "ann@example.com", "first_name": "a" * (limit + 1)}]
            )

        assert error.value.code == "invalid_input"
        assert not ProfileUserRole.objects.filter(profile=profile).exists()

    def test_a_row_reused_for_someone_else_drops_the_previous_names(self, profile) -> None:
        former = UserFactory(email="old@example.com")
        ProfileUserRoleFactory(
            profile=profile,
            user=former,
            role=MANAGER,
            status=Status.DECLINED,
            invited_email="old@example.com",
            invited_first_name="Former",
            invited_last_name="Holder",
        )
        former.email = "new@example.com"
        former.save()

        invitation = invite(profile, "old@example.com")

        assert invitation.invited_first_name == ""
        assert invitation.invited_last_name == ""

    def test_a_fresh_invitation_to_an_address_without_an_account_drops_earlier_names(
        self, profile
    ) -> None:
        # Nobody can tell whether the address still belongs to the person named before.
        expired = ProfileUserRoleFactory(
            profile=profile,
            user=None,
            role=MANAGER,
            status=Status.EXPIRED,
            invited_email="ann@example.com",
            invited_first_name="Ann",
            invited_last_name="Lee",
        )

        invitation = invite(profile)

        assert invitation.pk == expired.pk
        assert invitation.invited_first_name == ""
        assert invitation.invited_last_name == ""

    def test_a_batch_keeps_the_callers_order(self, profile) -> None:
        result = service.send_invitations(profile, ["zoe@example.com", "ann@example.com"])

        assert [row.invited_email for row in result.invitations] == [
            "zoe@example.com",
            "ann@example.com",
        ]

    def test_a_resend_waits_for_the_interval_after_the_latest_attempt(
        self, profile, settings
    ) -> None:
        invitation = invite(profile)
        ProfileUserRole.objects.filter(pk=invitation.pk).update(
            last_sent_at=timezone.now() - timedelta(days=1)
        )
        settings.BASEAPP_PROFILES_INVITATION_RESEND_MIN_INTERVAL = 300

        with pytest.raises(ProfileMembershipError) as error:
            service.resend_invitation(invitation)

        assert error.value.code == "resend_too_soon"

    def test_an_in_place_resend_rebinds_whoever_holds_the_address_now(self, profile) -> None:
        account = UserFactory(email="old@example.com")
        invitation = invite(profile, "old@example.com")
        assert invitation.user == account
        account.email = "new@example.com"
        account.save()

        resent = service.resend_invitation(invitation).invitations[0]

        assert resent.pk == invitation.pk
        assert resent.user is None

    def test_an_email_that_left_for_a_replaced_token_is_not_counted(self, profile) -> None:
        invitation = invite(profile)
        stale = stale_copy(invitation)
        service.resend_invitation(invitation)
        counted = ProfileUserRole.objects.get(pk=invitation.pk)

        assert service.send_invitation_email_now(stale) is True

        after = ProfileUserRole.objects.get(pk=invitation.pk)
        assert after.sent_count == counted.sent_count
        assert after.last_sent_at == counted.last_sent_at

    def test_member_search_matches_email_and_profile_name(self, profile) -> None:
        from baseapp_profiles.rest_framework.memberships.filters import ProfileMemberFilter

        ann = ProfileUserRoleFactory(profile=profile, user=UserFactory(email="ann@example.com"))
        ProfileUserRoleFactory(profile=profile, user=UserFactory(email="bob@example.com"))

        found = ProfileMemberFilter({"q": "ann@"}, queryset=ProfileUserRole.objects.all()).qs

        assert list(found) == [ann]


class TestOrganizationProfileName:
    def test_the_profile_is_named_from_the_stored_organization(self) -> None:
        from baseapp_organizations.services import OrganizationService

        Organization = swapper.load_model("baseapp_organizations", "Organization")
        organization = Organization.objects.create(name="Acme")
        stale = Organization.objects.get(pk=organization.pk)
        Organization.objects.filter(pk=organization.pk).update(name="Acme Holdings")

        profile = OrganizationService.ensure_profile(stale)

        assert profile.name == "Acme Holdings"


class TestFourthRound:
    def test_a_claim_is_not_resent_to_an_address_its_account_left(self, profile, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_CAN_INVITE_MEMBER = lambda membership: True
        member = UserFactory(email="old@example.com", is_active=False)
        membership = ProfileUserRoleFactory(
            profile=profile, user=member, role=MANAGER, status=Status.ACTIVE
        )
        claim = invite(profile, "old@example.com")
        assert claim.pk == membership.pk
        member.email = "new@example.com"
        member.save()
        token = claim.invitation_token

        with pytest.raises(ProfileMembershipError) as error:
            service.resend_invitation(claim)

        assert error.value.code == "invalid_invitation"
        membership.refresh_from_db()
        assert membership.invitation_token == token
        assert membership.user == member

    def test_cancel_reports_the_invitation_as_it_is_now(
        self, profile, settings, signal_recorder, django_capture_on_commit_callbacks
    ) -> None:
        settings.BASEAPP_PROFILES_INVITATION_KEEP_HISTORY = True
        invitation = invite(profile)
        stale = stale_copy(invitation)
        current_token = service.resend_invitation(invitation).invitations[0].invitation_token
        assert stale.invitation_token != current_token
        cancelled = signal_recorder(signals.invitation_cancelled)

        with django_capture_on_commit_callbacks(execute=True):
            result = service.cancel_invitation(stale)

        assert result.invitation_token == current_token
        assert cancelled[0]["instance"].invitation_token == current_token
        assert result.status == Status.CANCELLED

    def test_a_release_that_expired_in_the_queue_can_be_released_again(
        self, profile, settings, django_capture_on_commit_callbacks, mailoutbox
    ) -> None:
        settings.BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK = hold_everything
        held = invite(profile)
        settings.BASEAPP_PROFILES_INVITATION_ASYNC_SEND = True
        settings.CELERY_TASK_ALWAYS_EAGER = False
        with patch.object(tasks.send_invitation_email_task, "delay") as delay:
            with django_capture_on_commit_callbacks(execute=True):
                service.release_invitation(held)
        args = list(delay.call_args.args)
        # The queue was slow: the lifetime ran out, and the sweep got there first.
        past = timezone.now() - timedelta(minutes=5)
        ProfileUserRole.objects.filter(pk=held.pk).update(invitation_expires_at=past)
        args[3] = past.isoformat()
        service.expire_invitations()

        assert tasks.send_invitation_email_task(*args) is False

        held.refresh_from_db()
        assert held.status == Status.PENDING
        assert held.invitation_expires_at is None
        assert mailoutbox == []

    def test_a_deep_link_answer_that_is_not_json_falls_back(self, profile, settings) -> None:
        from baseapp_profiles.emails import get_accept_url

        invitation = invite(profile)

        with patch("baseapp_core.deep_links.requests.post") as post:
            post.return_value.json.side_effect = ValueError("no JSON")
            url = get_accept_url(invitation)

        assert url == settings.FRONT_ACCEPT_INVITATION_URL.format(token=invitation.invitation_token)

    def test_a_prefetch_keeps_the_order_it_asked_for(self, profile) -> None:
        from django.db.models import Prefetch

        Profile = swapper.load_model("baseapp_profiles", "Profile")
        URLPath = profile.url_paths.model
        profile.url_paths.all().delete()
        first = URLPath.objects.create(target=profile, path="/acme-one", is_active=True)
        second = URLPath.objects.create(target=profile, path="/acme-two", is_active=True)

        plain = Profile.objects.prefetch_related("url_paths").get(pk=profile.pk)
        newest_first = Profile.objects.prefetch_related(
            Prefetch("url_paths", queryset=URLPath.objects.order_by("-pk"))
        ).get(pk=profile.pk)

        assert plain.url_path == first == profile.url_path
        assert newest_first.url_path == second
