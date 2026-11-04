"""`BASEAPP_PROFILES_INVITATION_EXPIRATION_DAYS`: one expiry rule for every send path."""

from datetime import timedelta

import pytest
import swapper
from django.utils import timezone

from baseapp_profiles import conf, emails
from baseapp_profiles.services import invitations as service

from .factories import ProfileFactory

pytestmark = pytest.mark.django_db

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
Status = ProfileUserRole.ProfileRoleStatus

EXPIRY_DAYS = {"value": 30}


def project_expiry_days() -> int:
    return EXPIRY_DAYS["value"]


def lifetime(invitation) -> timedelta:
    return invitation.invitation_expires_at - invitation.invited_at


def assert_lifetime_days(invitation, days: int) -> None:
    assert abs(lifetime(invitation) - timedelta(days=days)) < timedelta(seconds=5)


@pytest.fixture
def profile() -> "ProfileFactory":
    return ProfileFactory()


class TestExpirationDays:
    def test_defaults_to_seven_days(self, profile, settings) -> None:
        if hasattr(settings, "INVITATION_EXPIRATION_DAYS"):
            del settings.INVITATION_EXPIRATION_DAYS
        invitation = service.send_invitations(profile, ["ann@example.com"]).invitations[0]

        assert conf.invitation_expiration_days() == 7
        assert_lifetime_days(invitation, 7)

    def test_falls_back_to_the_legacy_setting(self, profile, settings) -> None:
        settings.INVITATION_EXPIRATION_DAYS = 3

        invitation = service.send_invitations(profile, ["ann@example.com"]).invitations[0]

        assert_lifetime_days(invitation, 3)

    def test_the_new_setting_wins_over_the_legacy_one(self, profile, settings) -> None:
        settings.INVITATION_EXPIRATION_DAYS = 3
        settings.BASEAPP_PROFILES_INVITATION_EXPIRATION_DAYS = 10

        invitation = service.send_invitations(profile, ["ann@example.com"]).invitations[0]

        assert_lifetime_days(invitation, 10)

    def test_a_callable_is_read_on_every_send(self, profile, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_EXPIRATION_DAYS = project_expiry_days
        EXPIRY_DAYS["value"] = 30
        first = service.send_invitations(profile, ["ann@example.com"]).invitations[0]

        EXPIRY_DAYS["value"] = 2
        second = service.send_invitations(profile, ["bob@example.com"]).invitations[0]

        assert_lifetime_days(second, 2)
        # Invitations already sent keep the date they were given.
        first.refresh_from_db()
        assert_lifetime_days(first, 30)

    def test_a_dotted_path_is_imported(self, profile, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_EXPIRATION_DAYS = (
            "baseapp_profiles.tests.test_invitation_expiry.project_expiry_days"
        )
        EXPIRY_DAYS["value"] = 12

        invitation = service.send_invitations(profile, ["ann@example.com"]).invitations[0]

        assert_lifetime_days(invitation, 12)

    def test_resend_and_release_use_the_current_value(self, profile, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_EXPIRATION_DAYS = 5
        invitation = service.send_invitations(profile, ["ann@example.com"]).invitations[0]

        settings.BASEAPP_PROFILES_INVITATION_EXPIRATION_DAYS = 9
        invitation = service.resend_invitation(invitation).invitations[0]
        assert_lifetime_days(invitation, 9)

        invitation.invitation_expires_at = None
        invitation.save(update_fields=["invitation_expires_at"])
        settings.BASEAPP_PROFILES_INVITATION_EXPIRATION_DAYS = 4
        service.release_invitation(invitation)
        invitation.refresh_from_db()
        assert invitation.invitation_expires_at - timezone.now() > timedelta(days=3, hours=23)
        assert invitation.invitation_expires_at - timezone.now() < timedelta(days=4)

    def test_the_legacy_create_invitation_uses_it(self, profile, settings) -> None:
        settings.BASEAPP_PROFILES_INVITATION_EXPIRATION_DAYS = 21

        invitation = emails.create_invitation(profile, None, "Ann@Example.com")

        assert invitation.status == Status.PENDING
        assert_lifetime_days(invitation, 21)

    def test_the_deprecated_constant_follows_the_setting(self, settings) -> None:
        from baseapp_profiles import constants

        settings.BASEAPP_PROFILES_INVITATION_EXPIRATION_DAYS = 11

        with pytest.warns(DeprecationWarning):
            assert constants.INVITATION_EXPIRATION_DAYS == 11
