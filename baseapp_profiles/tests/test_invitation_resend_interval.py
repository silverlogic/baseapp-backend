"""`BASEAPP_PROFILES_INVITATION_RESEND_MIN_INTERVAL`: no resending in quick succession."""

from datetime import timedelta

import pytest
import swapper
from django.utils import timezone

from baseapp_profiles.exceptions import ProfileMembershipError
from baseapp_profiles.services import invitations as service

from .factories import ProfileFactory

pytestmark = pytest.mark.django_db

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")


@pytest.fixture
def invitation() -> "ProfileUserRole":
    return service.send_invitations(ProfileFactory(), ["ann@example.com"]).invitations[0]


def sent_ago(invitation, seconds: int) -> None:
    invitation.last_sent_at = timezone.now() - timedelta(seconds=seconds)
    invitation.save(update_fields=["last_sent_at"])


def test_resends_are_not_limited_by_default(invitation, mailoutbox) -> None:
    service.resend_invitation(invitation)
    service.resend_invitation(invitation)

    assert len(mailoutbox) == 3


def test_a_resend_too_soon_is_refused(invitation, settings, mailoutbox) -> None:
    settings.BASEAPP_PROFILES_INVITATION_RESEND_MIN_INTERVAL = 300
    token = invitation.invitation_token
    sent_ago(invitation, 60)

    with pytest.raises(ProfileMembershipError) as excinfo:
        service.resend_invitation(invitation)

    assert excinfo.value.code == "resend_too_soon"
    invitation.refresh_from_db()
    assert invitation.invitation_token == token
    assert len(mailoutbox) == 1


def test_a_resend_after_the_interval_goes_out(invitation, settings, mailoutbox) -> None:
    settings.BASEAPP_PROFILES_INVITATION_RESEND_MIN_INTERVAL = 300
    sent_ago(invitation, 301)

    result = service.resend_invitation(invitation)

    assert result.emails_sent == 1


def test_a_never_sent_invitation_counts_from_when_it_was_opened(settings) -> None:
    settings.BASEAPP_PROFILES_INVITATION_PRE_SEND_HOOK = lambda invitation: True
    held = service.send_invitations(ProfileFactory(), ["ann@example.com"]).held[0]
    settings.BASEAPP_PROFILES_INVITATION_RESEND_MIN_INTERVAL = 300

    with pytest.raises(ProfileMembershipError) as excinfo:
        service.resend_invitation(held)

    assert excinfo.value.code == "resend_too_soon"


def test_graphql_reports_the_code(django_user_client, graphql_user_client, settings) -> None:
    settings.BASEAPP_PROFILES_INVITATION_RESEND_MIN_INTERVAL = 300
    invitation = service.send_invitations(
        ProfileFactory(owner=django_user_client.user), ["ann@example.com"]
    ).invitations[0]

    content = graphql_user_client(
        """
        mutation Resend($input: ProfileResendInvitationInput!) {
            profileResendInvitation(input: $input) { emailSent }
        }
        """,
        variables={"input": {"invitationId": invitation.relay_id}},
    ).json()

    assert content["errors"][0]["extensions"]["code"] == "resend_too_soon"
