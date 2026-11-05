from datetime import datetime
from datetime import timezone as dt_timezone
from unittest.mock import patch

import pytest
import swapper
from django.utils import translation

from baseapp_core.exceptions import DeepLinkFetchError
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.emails import create_invitation, send_invitation_email
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
ENGLISH_MONTHS = [
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
]  # fmt: skip


def translated(language: str, msgid: str) -> str:
    with translation.override(language):
        text = translation.gettext(msgid)
    assert text != msgid, f"{msgid!r} has no {language} translation"
    return text


@pytest.fixture
def invitation():
    inviter = UserFactory(preferred_language="en")
    profile = ProfileFactory(owner=inviter, name="Acme")
    invitation = create_invitation(profile, inviter, "invitee@example.com")
    invitation.invitation_expires_at = datetime(2030, 3, 5, 12, tzinfo=dt_timezone.utc)
    invitation.save()
    return invitation


@pytest.mark.parametrize("language", ["es", "pt"])
def test_invitation_email_is_fully_localized(language, invitation, outbox) -> None:
    invited = UserFactory(email=invitation.invited_email, preferred_language=language)
    invitation.user = invited
    invitation.save()

    with patch("baseapp_profiles.emails.get_deep_link", side_effect=DeepLinkFetchError):
        send_invitation_email(invitation, invitation.profile.owner)

    assert len(outbox) == 1
    body = outbox[0].body
    assert translated(language, "Hi there,") in body
    assert translated(language, "manager") in body
    assert "March" not in body
    assert not any(month in body for month in ENGLISH_MONTHS)
    with translation.override(language):
        assert translation.gettext("March").lower() in body.lower()


def test_invitation_email_falls_back_to_the_inviters_language(invitation, outbox) -> None:
    invitation.profile.owner.preferred_language = "es"
    invitation.profile.owner.save()

    with patch("baseapp_profiles.emails.get_deep_link", side_effect=DeepLinkFetchError):
        send_invitation_email(invitation, invitation.profile.owner)

    assert translated("es", "Hi there,") in outbox[0].body
