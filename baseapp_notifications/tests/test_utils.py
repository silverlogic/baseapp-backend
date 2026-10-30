from unittest.mock import patch

import pytest
import swapper
from django.utils import translation

from baseapp_core.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

Notification = swapper.load_model("notifications", "Notification")


def test_send_notification_add_to_history(send_notification) -> None:
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


def test_send_email_notification(
    outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    user = UserFactory()

    description = "this is my description"
    with django_capture_on_commit_callbacks(execute=True):
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


def test_send_email_notification_can_customize_templates(
    outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    user = UserFactory()

    with django_capture_on_commit_callbacks(execute=True):
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


def test_send_email_and_add_to_history_mark_notification_as_emailed(
    outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    user = UserFactory()

    with django_capture_on_commit_callbacks(execute=True):
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


def test_send_push_notification(send_notification, django_capture_on_commit_callbacks) -> None:
    user = UserFactory()

    with patch("baseapp_notifications.tasks.send_push_notification.delay") as mock:
        with django_capture_on_commit_callbacks(execute=True):
            send_notification(
                sender=user,
                recipient=user,
                verb="sent as push",
                add_to_history=False,
                send_email=False,
                send_push=True,
            )
        assert mock.called


def test_can_override_email_subject(
    outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    user = UserFactory()

    with django_capture_on_commit_callbacks(execute=True):
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


def test_can_override_email_message(
    outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    user = UserFactory()

    with django_capture_on_commit_callbacks(execute=True):
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


@pytest.mark.parametrize("language", ["es", "pt"])
def test_send_email_notification_uses_recipient_language(
    language, outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    recipient = UserFactory(preferred_language=language)
    with translation.override(language):
        see_on_app = translation.gettext("See on App")
    assert see_on_app != "See on App"

    translation.activate("en")
    # Notification emails are sent once the transaction commits.
    with django_capture_on_commit_callbacks(execute=True):
        send_notification(
            sender=recipient,
            recipient=recipient,
            verb="sent to email",
            description="this is my description",
            notification_url="https://example.com",
            add_to_history=False,
            send_email=True,
            send_push=False,
        )

    assert len(outbox) == 1
    html = outbox[0].alternatives[0][0]
    assert see_on_app in html
    assert "See on App" not in html
    assert translation.get_language() == "en"
