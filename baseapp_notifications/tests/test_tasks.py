from unittest.mock import patch

import pytest
from push_notifications.models import APNSDevice, GCMDevice, WebPushDevice, WNSDevice

from baseapp_core.tests.factories import UserFactory
from baseapp_notifications.tasks import send_push_notification

pytestmark = pytest.mark.django_db


def test_push_requires_description() -> None:
    with pytest.raises(Exception, match="push_description is required"):
        send_push_notification(UserFactory().id)


def test_push_to_web_only_user_sends_plain_message() -> None:
    user = UserFactory()
    WebPushDevice.objects.create(
        user=user, registration_id="https://push.example.com/1", p256dh="key", auth="auth"
    )

    with patch("push_notifications.models.WebPushDeviceQuerySet.send_message") as send:
        send_push_notification(user.id, push_title="Title", push_description="Body")

    send.assert_called_once_with(message="Body", extra=None)


def test_push_to_windows_only_user_sends_plain_message() -> None:
    user = UserFactory()
    WNSDevice.objects.create(user=user, registration_id="https://wns.example.com/1")

    with patch("push_notifications.models.WNSDeviceQuerySet.send_message") as send:
        send_push_notification(user.id, push_description="Body", extra={"a": 1})

    send.assert_called_once_with(message="Body", extra={"a": 1})


def test_push_title_only_changes_apple_and_android_payloads() -> None:
    user = UserFactory()
    APNSDevice.objects.create(user=user, registration_id="apns-1")
    GCMDevice.objects.create(user=user, registration_id="gcm-1", cloud_message_type="FCM")
    WNSDevice.objects.create(user=user, registration_id="https://wns.example.com/1")

    with (
        patch("push_notifications.models.APNSDeviceQuerySet.send_message") as apple,
        patch("push_notifications.models.GCMDeviceQuerySet.send_message") as android,
        patch("push_notifications.models.WNSDeviceQuerySet.send_message") as windows,
    ):
        send_push_notification(user.id, push_title="Title", push_description="Body")

    apple.assert_called_once_with(message={"title": "Title", "body": "Body"}, extra=None)
    android.assert_called_once_with("Body", title="Title", extra=None)
    windows.assert_called_once_with(message="Body", extra=None)


def test_push_without_title_sends_plain_message_to_apple_and_android() -> None:
    user = UserFactory()
    APNSDevice.objects.create(user=user, registration_id="apns-1")
    GCMDevice.objects.create(user=user, registration_id="gcm-1", cloud_message_type="FCM")

    with (
        patch("push_notifications.models.APNSDeviceQuerySet.send_message") as apple,
        patch("push_notifications.models.GCMDeviceQuerySet.send_message") as android,
    ):
        send_push_notification(user.id, push_description="Body")

    apple.assert_called_once_with(message="Body", extra=None)
    android.assert_called_once_with(message="Body", extra=None)
