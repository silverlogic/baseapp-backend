from unittest.mock import patch

import pytest
import swapper

from baseapp_core.tests.factories import UserFactory

from ..utils import send_notification

pytestmark = pytest.mark.django_db

Notification = swapper.load_model("notifications", "Notification")


def test_send_notification_add_to_history():
    user = UserFactory()

    send_notification(
        sender=user,
        recipient=user,
        verb="added to history",
        add_to_history=True,
        send_email=False,
        send_push=False,
    )

    notification = Notification.objects.first()
    assert notification.verb == "added to history"


def test_send_email_notification(outbox):
    user = UserFactory()

    description = "this is my description"
    send_notification(
        sender=user,
        recipient=user,
        verb="sent to email",
        description=description,
        notification_url="https://example.com",
        add_to_history=False,
        send_email=True,
        send_push=False,
    )

    assert Notification.objects.first() is None
    assert len(outbox) == 1
    assert outbox[0].subject == description
    assert description in outbox[0].body
    assert description in outbox[0].alternatives[0][0]


def test_send_email_notification_can_customize_templates(outbox):
    user = UserFactory()

    send_notification(
        sender=user,
        recipient=user,
        verb="verb",
        description="this is my description",
        notification_url="https://example.com",
        add_to_history=False,
        send_email=True,
        send_push=False,
    )

    assert Notification.objects.first() is None
    assert len(outbox) == 1
    assert outbox[0].subject == "custom tempate subject"
    assert "custom txt message" in outbox[0].body
    assert "custom html message" in outbox[0].alternatives[0][0]


def test_send_email_and_add_to_history_mark_notification_as_emailed(outbox):
    user = UserFactory()

    send_notification(
        sender=user,
        recipient=user,
        verb="sent to email",
        description="this is my description",
        notification_url="https://example.com",
        add_to_history=True,
        send_email=True,
        send_push=False,
    )

    notification = Notification.objects.first()

    assert notification.emailed is True
    assert len(outbox) == 1


def test_send_push_notification():
    user = UserFactory()

    with patch("baseapp_notifications.utils.send_push_notification.delay") as mock:
        send_notification(
            sender=user,
            recipient=user,
            verb="sent as push",
            add_to_history=False,
            send_email=False,
            send_push=True,
        )
        assert mock.called


def test_can_override_email_subject(outbox):
    user = UserFactory()

    send_notification(
        sender=user,
        recipient=user,
        verb="default template verb",
        add_to_history=False,
        send_email=True,
        send_push=False,
        email_subject="custom subject",
    )

    assert outbox[0].subject == "custom subject"


def test_can_override_email_message(outbox):
    user = UserFactory()

    send_notification(
        sender=user,
        recipient=user,
        verb="default template verb",
        add_to_history=False,
        send_email=True,
        send_push=False,
        email_message="custom message",
    )

    assert "custom message" in outbox[0].body
