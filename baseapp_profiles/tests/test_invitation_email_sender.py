"""`BASEAPP_PROFILES_INVITATION_EMAIL_SENDER` and `emails.get_accept_url`."""

from unittest.mock import patch

import pytest
import swapper

from baseapp_core.exceptions import DeepLinkFetchError
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles import emails, signals, tasks
from baseapp_profiles.services import invitations as service

from .factories import ProfileFactory

pytestmark = pytest.mark.django_db

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")

SENT = []


def project_sender(invitation, inviter) -> None:
    SENT.append((invitation.pk, getattr(inviter, "pk", None), emails.get_accept_url(invitation)))


def failing_sender(invitation, inviter) -> None:
    raise RuntimeError("mail provider down")


@pytest.fixture(autouse=True)
def reset_sent() -> None:
    SENT.clear()


@pytest.fixture(autouse=True)
def no_deep_links() -> None:
    with patch("baseapp_profiles.emails.get_deep_link", side_effect=DeepLinkFetchError):
        yield


@pytest.fixture
def custom_sender(settings) -> None:
    settings.BASEAPP_PROFILES_INVITATION_EMAIL_SENDER = (
        "baseapp_profiles.tests.test_invitation_email_sender.project_sender"
    )


class TestEmailSender:
    def test_default_sender_emails_the_invitee(self, mailoutbox) -> None:
        result = service.send_invitations(ProfileFactory(name="Acme"), ["ann@example.com"])

        assert result.emails_sent == 1
        assert mailoutbox[0].to == ["ann@example.com"]
        assert result.invitations[0].invitation_token in mailoutbox[0].body

    def test_custom_sender_replaces_the_email(
        self,
        custom_sender,
        mailoutbox,
        signal_recorder,
        settings,
        django_capture_on_commit_callbacks,
    ) -> None:
        sent = signal_recorder(signals.invitation_sent)
        inviter = UserFactory()

        with django_capture_on_commit_callbacks(execute=True):
            result = service.send_invitations(
                ProfileFactory(), ["ann@example.com"], invited_by=inviter
            )
        invitation = result.invitations[0]

        assert mailoutbox == []
        assert result.emails_sent == 1
        assert SENT == [
            (
                invitation.pk,
                inviter.pk,
                settings.FRONT_ACCEPT_INVITATION_URL.format(token=invitation.invitation_token),
            )
        ]
        invitation.refresh_from_db()
        assert invitation.sent_count == 1
        assert len(sent) == 1

    def test_a_callable_works_too(self, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_EMAIL_SENDER = project_sender

        service.send_invitations(ProfileFactory(), ["ann@example.com"])

        assert len(SENT) == 1

    def test_a_failing_sender_is_not_counted(self, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_EMAIL_SENDER = failing_sender

        result = service.send_invitations(ProfileFactory(), ["ann@example.com"])

        assert result.emails_sent == 0
        assert ProfileUserRole.objects.get().sent_count == 0

    def test_the_celery_task_uses_it(self, custom_sender) -> None:
        inviter = UserFactory()
        invitation = ProfileUserRole.objects.create(
            profile=ProfileFactory(),
            invited_email="ann@example.com",
            status=ProfileUserRole.ProfileRoleStatus.PENDING,
            invitation_token="tok",
        )

        assert tasks.send_invitation_email_task(invitation.pk, inviter.pk) is True
        assert SENT[0][:2] == (invitation.pk, inviter.pk)


class TestAcceptUrl:
    def test_falls_back_to_the_frontend_url(self, settings) -> None:
        invitation = ProfileUserRole(invitation_token="abc")

        assert emails.get_accept_url(invitation) == settings.FRONT_ACCEPT_INVITATION_URL.format(
            token="abc"
        )

    def test_uses_the_deep_link_when_there_is_one(self) -> None:
        invitation = ProfileUserRole(invitation_token="abc")

        with patch(
            "baseapp_profiles.emails.get_deep_link", return_value={"url": "https://app.link/x"}
        ):
            assert emails.get_accept_url(invitation) == "https://app.link/x"
