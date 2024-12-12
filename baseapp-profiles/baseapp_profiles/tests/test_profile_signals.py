import pytest
from .factories import ProfileFactory
from ..signals import notify_on_profile_update
from unittest.mock import patch

pytestmark = pytest.mark.django_db


@patch("baseapp_profiles.signals.send_reply_created_notification")
def test_profile_change_send_notifications(mock_send_notification):
    profile = ProfileFactory(owner__first_name="John", owner__last_name="Doe")
    profile.image = "changed-image.jpg"
    profile.banner_image = "changed-banner.jpg"
    profile.biography = "changed-biography"
    notify_on_profile_update(profile)

    assert mock_send_notification.delay.called
    args = mock_send_notification.delay.call_args
    assert args[0][0] == profile.pk
    assert args[0][1] == "John Doe updated banner_image, biography, image your profile."


@patch("baseapp_profiles.signals.send_reply_created_notification")
def test_profile_dont_notify_if_different_fields_changes(mock_send_notification):
    profile = ProfileFactory(owner__first_name="John", owner__last_name="Doe")
    profile.name = "changed name"
    notify_on_profile_update(profile)

    assert not mock_send_notification.delay.called
